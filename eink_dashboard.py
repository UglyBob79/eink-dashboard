import appdaemon.plugins.hass.hassapi as hass
from PIL import Image, ImageDraw, ImageFont
import os

# Display: Waveshare 7.5" V2 portrait
W, H = 480, 800

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


# ── Layout ────────────────────────────────────────────────────────────────────
#
#  Diagram anchored top-left (~500x390px), leaving right + bottom for future use
#
#               [SOLAR]
#                  ↓
#   [GRID] ──↔── [SYSTEM] ──→── [HOME]
#                  ↕
#              [BATTERY]
#
#                           | <- ~x=510 free space to the right ->
#
# Global offset for the entire power flow diagram
DIAGRAM_X =   0
DIAGRAM_Y =  30

def _pos(x, y):
    return (DIAGRAM_X + x, DIAGRAM_Y + y)

SOLAR_POS  = _pos(240,  80);  SOLAR_BOX  = (140,  80)
SYSTEM_POS = _pos(240, 215);  SYSTEM_BOX = (150, 120)
GRID_POS   = _pos( 75, 215);  GRID_BOX   = (110,  90)
HOME_POS   = _pos(405, 215);  HOME_BOX   = (110, 100)
BATT_POS   = _pos(240, 355);  BATT_BOX   = (160,  90)


class EinkDashboard(hass.Hass):

    def initialize(self):
        self.out_dir      = self.args.get("out_dir",    "/homeassistant/www")
        self.fonts_dir    = self.args.get("fonts_dir",  "/homeassistant/esphome/apps/dashboard/fonts")
        self.system_label = self.args.get("system_label", "SYSTEM")
        interval          = self.args.get("render_interval", 60)
        os.makedirs(self.out_dir, exist_ok=True)
        self.fonts = self._load_fonts()

        self.show_energy_today = self.args.get("show_energy_today", False)

        required = [
            "sensor_solar", "sensor_grid", "sensor_battery", "sensor_batt_soc",
            "sensor_load", "sensor_inverter_state",
            "status_grid_lost", "status_cat_box", "status_cat_box_dt", "status_pool_pump",
        ]
        if self.show_energy_today:
            required += ["sensor_solar_today", "sensor_import_daily", "sensor_export_daily"]

        missing = [k for k in required if k not in self.args]
        if missing:
            self.log(f"Missing required config keys: {missing}", level="ERROR")
            self._render_error_page("MISSING CONFIG KEYS", missing)
            return

        self.sensor_solar          = self.args["sensor_solar"]
        self.sensor_grid           = self.args["sensor_grid"]
        self.sensor_battery        = self.args["sensor_battery"]
        self.sensor_batt_soc       = self.args["sensor_batt_soc"]
        self.sensor_load           = self.args["sensor_load"]
        self.sensor_inverter_state = self.args["sensor_inverter_state"]
        self.sensor_solar_today    = self.args.get("sensor_solar_today")
        self.sensor_import_daily   = self.args.get("sensor_import_daily")
        self.sensor_export_daily   = self.args.get("sensor_export_daily")
        self.status_grid_lost      = self.args["status_grid_lost"]
        self.status_cat_box        = self.args["status_cat_box"]
        self.status_cat_box_dt     = self.args["status_cat_box_dt"]
        self.status_pool_pump      = self.args["status_pool_pump"]

        self.run_every(self._scheduled_render, "now", interval)

    def _scheduled_render(self, kwargs):
        self.generate()

    def generate(self):
        try:
            unavailable = self._check_entities()
            if unavailable:
                self.log(f"Unavailable entities: {unavailable}", level="WARNING")
                self._render_error_page("UNAVAILABLE ENTITIES", unavailable)
            else:
                self._render_power_page()
        except Exception as e:
            self.log(f"EinkDashboard render error: {e}", level="ERROR")

    def _check_entities(self):
        """Return list of entity IDs that are missing or unavailable."""
        entities = [
            self.sensor_solar, self.sensor_grid, self.sensor_battery,
            self.sensor_batt_soc, self.sensor_load, self.sensor_inverter_state,
            self.status_grid_lost, self.status_cat_box, self.status_cat_box_dt,
            self.status_pool_pump,
        ]
        if self.show_energy_today:
            entities += [self.sensor_solar_today, self.sensor_import_daily, self.sensor_export_daily]
        bad = []
        for e in entities:
            state = self.get_state(e)
            if state is None or state in ("unavailable", "unknown"):
                bad.append(e)
        return bad

    def _render_error_page(self, title, lines):
        img  = Image.new("RGB", (W, H), WHITE)
        draw = ImageDraw.Draw(img)
        f    = self.fonts

        draw.text((W // 2, 60), "\U000F0028", font=f["icon"], fill=BLACK, anchor="mm")
        draw.text((W // 2, 100), title, font=f["medium"], fill=BLACK, anchor="mm")
        draw.line([(20, 120), (W - 20, 120)], fill=BLACK, width=2)

        y = 148
        for line in lines:
            draw.text((W // 2, y), line, font=f["small"], fill=BLACK, anchor="mm")
            y += 22

        from datetime import datetime
        ts = datetime.now().strftime("Updated %Y-%m-%d %H:%M")
        draw.text((W // 2, H - 8), ts, font=f["label"], fill=BLACK, anchor="mb")

        img.save(f"{self.out_dir}/eink_page0.png")
        img_l = img.convert("L")
        img_land_l = img_l.transpose(Image.ROTATE_270)
        img_land_1bit = img_land_l.point(lambda x: 255 if x > 128 else 0, "1")
        with open(f"{self.out_dir}/eink_page0.bin", "wb") as fh:
            fh.write(img_land_1bit.tobytes())

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_power_page(self):
        img  = Image.new("RGB", (W, H), WHITE)
        draw = ImageDraw.Draw(img)
        f    = self.fonts

        solar_w   = self._float(self.sensor_solar)
        grid_w    = self._float(self.sensor_grid)
        battery_w = self._float(self.sensor_battery)
        soc       = self._float(self.sensor_batt_soc)
        load_w         = self._float(self.sensor_load)
        inverter_state = self.get_state(self.sensor_inverter_state) or ""

        # Flow logic
        solar_on    = solar_w   >  50
        load_on     = load_w    >  50
        charging    = battery_w < -50   # system → battery
        discharging = battery_w >  50   # battery → system

        if self.get_state(self.status_grid_lost) == "Alarm":
            grid_state = "LOST"
        elif grid_w > 50:
            grid_state = "IMPORT"
        elif grid_w < -50:
            grid_state = "EXPORT"
        else:
            grid_state = "IDLE"

        # ── Title ─────────────────────────────────────────────────────────
        icon_w = draw.textlength("\U000F140B", font=f["icon"])  # mdi-lightning-bolt
        text_w = draw.textlength("ENERGY", font=f["medium"])
        gap    = 8
        total  = icon_w + gap + text_w
        x      = (W - total) // 2
        ty     = 22   # vertical center for icon + text
        draw.text((x, ty), "\U000F140B", font=f["icon"],   fill=BLACK, anchor="lm")
        draw.text((x + icon_w + gap, ty), "ENERGY", font=f["medium"], fill=BLACK, anchor="lm")
        draw.line([(20, ty + 22), (W - 20, ty + 22)], fill=BLACK, width=2)

        # ── Arrows (drawn before boxes so box borders cover line ends) ────

        # Solar → System (down)
        self._arrow_down(draw,
                         SOLAR_POS[0],
                         SOLAR_POS[1]  + SOLAR_BOX[1]  // 2,
                         SYSTEM_POS[1] - SYSTEM_BOX[1] // 2,
                         active=solar_on)

        # Grid ↔ System (horizontal)
        x_gap_left  = GRID_POS[0]   + GRID_BOX[0]   // 2
        x_gap_right = SYSTEM_POS[0] - SYSTEM_BOX[0] // 2
        if grid_state == "IMPORT":
            self._arrow_right(draw, x_gap_left, x_gap_right, GRID_POS[1], active=True)
        elif grid_state == "EXPORT":
            self._arrow_left(draw, x_gap_left, x_gap_right, GRID_POS[1], active=True)
        else:
            self._arrow_left(draw, x_gap_left, x_gap_right, GRID_POS[1], active=False)

        # System → Home (right)
        self._arrow_right(draw,
                          SYSTEM_POS[0] + SYSTEM_BOX[0] // 2,
                          HOME_POS[0]   - HOME_BOX[0]   // 2,
                          SYSTEM_POS[1],
                          active=load_on)

        # Battery ↔ System (vertical)
        y_gap_top = SYSTEM_POS[1] + SYSTEM_BOX[1] // 2
        y_gap_bot = BATT_POS[1]   - BATT_BOX[1]   // 2
        if charging:
            self._arrow_down(draw, BATT_POS[0], y_gap_top, y_gap_bot, active=True)
        else:
            self._arrow_up(draw, BATT_POS[0], y_gap_top, y_gap_bot, active=discharging)

        # ── Boxes ─────────────────────────────────────────────────────────

        self._box(draw, f, *SOLAR_POS, *SOLAR_BOX,
                  "SOLAR", f"{int(solar_w)} W",
                  filled=solar_on)

        self._box(draw, f, *SYSTEM_POS, *SYSTEM_BOX,
                  "SYSTEM", self.system_label,
                  sub=inverter_state.upper(),
                  filled=True)  # inverter hub — always highlighted

        self._box(draw, f, *GRID_POS, *GRID_BOX,
                  "GRID", f"{int(abs(grid_w))} W",
                  sub=grid_state,
                  filled=(grid_state == "IMPORT"))
        if grid_state == "LOST":
            bx = GRID_POS[0] + GRID_BOX[0] // 2 - 5
            by = GRID_POS[1] + GRID_BOX[1] // 2 - 5
            r  = 16
            draw.ellipse([bx - r, by - r, bx + r, by + r], fill=BLACK, outline=WHITE, width=2)
            draw.text((bx, by), "\U000F0028", font=f["icon"], fill=WHITE, anchor="mm")

        self._box(draw, f, *HOME_POS, *HOME_BOX,
                  "HOME", f"{int(load_w)} W")

        batt_sub = "CHARGING" if charging else ("DISCHARGING" if discharging else "IDLE")
        self._box(draw, f, *BATT_POS, *BATT_BOX,
                  "BATTERY", f"{int(soc)}%",
                  sub=f"{int(abs(battery_w))} W  ·  {batt_sub}",
                  filled=discharging)
        self._battery_poles(draw, f, *BATT_POS, *BATT_BOX)

        # ── Energy today strip (below battery, above statuses) ───────────
        if self.show_energy_today:
            solar_today  = self._float(self.sensor_solar_today)
            import_today = self._float(self.sensor_import_daily)
            export_today = self._float(self.sensor_export_daily)
            used_today   = max(0.0, import_today - export_today)

            strip_x0, strip_y0 = 20, 438
            strip_x1, strip_y1 = 460, 500
            col_w = (strip_x1 - strip_x0) // 4
            draw.rounded_rectangle([strip_x0, strip_y0, strip_x1, strip_y1],
                                    radius=10, fill=WHITE, outline=BLACK, width=2)

            energy_cols = [
                ("SOLAR",  f"{solar_today:.1f} kWh"),
                ("IMPORT", f"{import_today:.1f} kWh"),
                ("EXPORT", f"{export_today:.1f} kWh"),
                ("NET",    f"{used_today:.1f} kWh"),
            ]
            hdr_h = 22
            for i, (lbl, val) in enumerate(energy_cols):
                cx = strip_x0 + col_w * i + col_w // 2
                if i > 0:
                    div_x = strip_x0 + col_w * i
                    draw.line([(div_x, strip_y0 + 4), (div_x, strip_y1 - 4)], fill=BLACK, width=1)
                draw.text((cx, strip_y0 + hdr_h // 2), lbl, font=f["label"], fill=BLACK, anchor="mm")
                draw.line([(strip_x0 + col_w * i + 4,     strip_y0 + hdr_h),
                            (strip_x0 + col_w * (i + 1) - 4, strip_y0 + hdr_h)],
                           fill=BLACK, width=1)
                val_cy = strip_y0 + hdr_h + (strip_y1 - strip_y0 - hdr_h) // 2
                draw.text((cx, val_cy), val, font=f["medium"], fill=BLACK, anchor="mm")
            statuses_y = strip_y1 + 22
        else:
            statuses_y = BATT_POS[1] + BATT_BOX[1] // 2 + 30

        # ── Statuses header ───────────────────────────────────────────────
        sy = statuses_y
        _iw = draw.textlength("\U000F02FC", font=f["icon"])
        _tw = draw.textlength("STATUSES", font=f["medium"])
        _sx = (W - (_iw + 8 + _tw)) // 2
        draw.text((_sx, sy), "\U000F02FC", font=f["icon"],   fill=BLACK, anchor="lm")
        draw.text((_sx + _iw + 8, sy), "STATUSES", font=f["medium"], fill=BLACK, anchor="lm")
        draw.line([(20, sy + 22), (W - 20, sy + 22)], fill=BLACK, width=2)

        # ── Status rows ───────────────────────────────────────────────────
        row_y = sy + 22 + 26
        grid_val  = f"for {self._elapsed(self.status_grid_lost)}" if grid_state == "LOST" else f"OK · {self._elapsed(self.status_grid_lost)}"
        self._status_row(draw, f, row_y, "\U000F0D3E", "Grid lost", grid_val)
        row_y += 32

        cat_val = self._elapsed(self.status_cat_box_dt)
        self._status_row(draw, f, row_y, "\U000F011B", "Cat box emptied", cat_val)
        row_y += 32

        pump_on  = self.get_state(self.status_pool_pump) == "on"
        pump_val = f"for {self._elapsed(self.status_pool_pump)}" if pump_on else f"off · {self._elapsed(self.status_pool_pump)}"
        self._status_row(draw, f, row_y, "\U000F0606", "Pool pump", pump_val)
        row_y += 32

        # ── Timestamp ─────────────────────────────────────────────────────
        from datetime import datetime
        ts = datetime.now().strftime("Updated %Y-%m-%d %H:%M")
        draw.text((W // 2, H - 8), ts, font=f["label"], fill=BLACK, anchor="mb")

        # ── PNG: portrait, human-readable RGB ────────────────────────────
        img.save(f"{self.out_dir}/eink_page0.png")
        img_l = img.convert("L")

        # ── BIN: landscape, for ESP direct buffer write ───────────────────
        # Rotate grayscale BEFORE thresholding to avoid PIL re-thresholding
        # at 128 (which causes noise). ROTATE_270 = 90° CW matches the
        # physical 800×480 buffer layout (no rotation needed in ESPHome).
        # No XOR inversion — the waveshare V2 driver sends ~buffer[i],
        # so ESPHome's buffer convention (1=black) is already correct.
        img_land_l = img_l.transpose(Image.ROTATE_270)
        img_land_1bit = img_land_l.point(lambda x: 255 if x > 128 else 0, "1")
        with open(f"{self.out_dir}/eink_page0.bin", "wb") as fh:
            fh.write(img_land_1bit.tobytes())
        self.log("Rendered eink_page0.png + eink_page0.bin")

    # ── Box ───────────────────────────────────────────────────────────────────

    def _box(self, draw, f, cx, cy, bw, bh, label, value, sub=None, filled=False, icon=None):
        x0, y0 = cx - bw // 2, cy - bh // 2
        x1, y1 = cx + bw // 2, cy + bh // 2
        r = 14
        if filled:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=WHITE, outline=BLACK, width=3)
            tc = BLACK
        else:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=BLACK, outline=WHITE, width=3)
            tc = WHITE

        if icon:
            draw.text((cx, y0 + 10), icon, font=f["icon"], fill=tc, anchor="mt")
        else:
            draw.text((cx, y0 + 10), label, font=f["label"], fill=tc, anchor="mt")
        draw.line([(x0 + 8, y0 + 24), (x1 - 8, y0 + 24)], fill=tc, width=1)
        if value is not None:
            draw.text((cx, cy), value, font=f["large"], fill=tc, anchor="mm")
        if sub is not None:
            draw.text((cx, y1 - 10), sub, font=f["small"], fill=tc, anchor="mb")

    def _battery_poles(self, draw, f, cx, cy, bw, bh):
        box_top = cy - bh // 2
        pw, ph  = 20, 12   # pole width, height
        offset  = 45       # distance from center to each pole
        r       = 3

        for sign, dx in (("+", offset), ("−", -offset)):
            px = cx + dx
            # Pole sticking up above the box
            draw.rounded_rectangle(
                [px - pw // 2, box_top - ph, px + pw // 2, box_top + 2],
                radius=r, fill=BLACK, outline=WHITE, width=2)
            # Sign inside the box just below the pole
            draw.text((px, box_top + 14), sign, font=f["small"],
                      fill=WHITE, anchor="mm")

    # ── Directional arrows ────────────────────────────────────────────────────

    def _arrow_down(self, draw, cx, y_top, y_bot, active=True):
        if active:
            draw.line([(cx, y_top), (cx, y_bot - 14)], fill=BLACK, width=3)
            draw.polygon([(cx, y_bot), (cx-10, y_bot-16), (cx+10, y_bot-16)], fill=BLACK)
        else:
            self._dash_v(draw, cx, y_top, y_bot)

    def _arrow_up(self, draw, cx, y_top, y_bot, active=True):
        if active:
            draw.line([(cx, y_bot), (cx, y_top + 14)], fill=BLACK, width=3)
            draw.polygon([(cx, y_top), (cx-10, y_top+16), (cx+10, y_top+16)], fill=BLACK)
        else:
            self._dash_v(draw, cx, y_top, y_bot)

    def _arrow_right(self, draw, x_left, x_right, cy, active=True):
        if active:
            draw.line([(x_left, cy), (x_right - 14, cy)], fill=BLACK, width=3)
            draw.polygon([(x_right, cy), (x_right-16, cy-10), (x_right-16, cy+10)], fill=BLACK)
        else:
            self._dash_h(draw, x_left, x_right, cy)

    def _arrow_left(self, draw, x_left, x_right, cy, active=True):
        if active:
            draw.line([(x_right, cy), (x_left + 14, cy)], fill=BLACK, width=3)
            draw.polygon([(x_left, cy), (x_left+16, cy-10), (x_left+16, cy+10)], fill=BLACK)
        else:
            self._dash_h(draw, x_left, x_right, cy)

    # ── Dashed line helpers ───────────────────────────────────────────────────

    def _dash_v(self, draw, cx, y0, y1, dash=8, gap=5):
        y = y0
        while y < y1:
            draw.line([(cx, y), (cx, min(y + dash, y1))], fill=BLACK, width=1)
            y += dash + gap

    def _dash_h(self, draw, x0, x1, cy, dash=8, gap=5):
        x = x0
        while x < x1:
            draw.line([(x, cy), (min(x + dash, x1), cy)], fill=BLACK, width=1)
            x += dash + gap

    # ── Utilities ─────────────────────────────────────────────────────────────

    def _elapsed(self, entity):
        """Return smart-unit string for time since entity last changed state."""
        from datetime import datetime, timezone
        raw = self.get_state(entity, attribute="last_changed")
        if raw is None:
            return "—"
        if isinstance(raw, str):
            from dateutil.parser import parse
            dt = parse(raw)
        else:
            dt = raw
        secs = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
        if secs < 60:
            return f"{secs}s"
        elif secs < 3600:
            return f"{secs // 60}m"
        elif secs < 86400:
            return f"{secs // 3600}h"
        else:
            return f"{secs // 86400}d"

    def _status_row(self, draw, f, y, icon, label, value, margin=20, gap=6):
        """Draw a single status row: icon  label: value"""
        iw = draw.textlength(icon, font=f["icon_sm"])
        draw.text((margin, y), icon, font=f["icon_sm"], fill=BLACK, anchor="lm")
        draw.text((margin + iw + gap, y), f"{label}: {value}", font=f["status_text"], fill=BLACK, anchor="lm")

    def _float(self, entity, default=0.0):
        try:
            return float(self.get_state(entity))
        except (ValueError, TypeError):
            return default

    def _load_fonts(self):
        bold = f"{self.fonts_dir}/GothamRnd-Bold.ttf"
        book = f"{self.fonts_dir}/GothamRnd-Book.ttf"
        mdi = f"{self.fonts_dir}/materialdesignicons-webfont.ttf"
        try:
            return {
                "large":  ImageFont.truetype(bold, 24),
                "medium": ImageFont.truetype(bold, 22),
                "small":  ImageFont.truetype(book, 13),
                "label":  ImageFont.truetype(book, 12),
                "icon":        ImageFont.truetype(mdi, 28),
                "icon_sm":     ImageFont.truetype(mdi, 22),
                "status_text": ImageFont.truetype(book, 18),
            }
        except Exception as e:
            self.log(f"Font load failed, using default: {e}", level="WARNING")
            d = ImageFont.load_default()
            return {"large": d, "medium": d, "small": d, "label": d, "icon": d, "icon_sm": d, "status_text": d}
