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


# ── Component system ──────────────────────────────────────────────────────────

COMPONENT_REGISTRY = {}

def _register(name):
    def decorator(cls):
        COMPONENT_REGISTRY[name] = cls
        return cls
    return decorator


class Component:
    def entities(self):
        return []

    def render(self, draw, fonts, y):
        raise NotImplementedError


@_register("power_diagram")
class PowerDiagram(Component):
    def __init__(self, config, hass):
        self._hass           = hass
        self._system_label   = config.get("system_label", "SYSTEM")
        sensors              = config.get("sensors", {})
        self._solar          = sensors["solar"]
        self._grid           = sensors["grid"]
        self._battery        = sensors["battery"]
        self._batt_soc       = sensors["batt_soc"]
        self._load           = sensors["load"]
        self._inverter_state = sensors["inverter_state"]
        self._grid_lost      = sensors["grid_lost"]

    def entities(self):
        return [
            self._solar, self._grid, self._battery,
            self._batt_soc, self._load, self._inverter_state,
            self._grid_lost,
        ]

    def render(self, draw, fonts, y):
        hass = self._hass
        solar_w        = hass._float(self._solar)
        grid_w         = hass._float(self._grid)
        battery_w      = hass._float(self._battery)
        soc            = hass._float(self._batt_soc)
        load_w         = hass._float(self._load)
        inverter_state = hass.get_state(self._inverter_state) or ""

        solar_on    = solar_w   >  50
        load_on     = load_w    >  50
        charging    = battery_w < -50   # system → battery
        discharging = battery_w >  50   # battery → system

        if hass.get_state(self._grid_lost) == "Alarm":
            grid_state = "LOST"
        elif grid_w > 50:
            grid_state = "IMPORT"
        elif grid_w < -50:
            grid_state = "EXPORT"
        else:
            grid_state = "IDLE"

        hass._render_section_header(draw, fonts, 22, "\U000F140B", "ENERGY")

        # ── Arrows (drawn before boxes so box borders cover line ends) ────

        self._arrow_down(draw,
                         SOLAR_POS[0],
                         SOLAR_POS[1]  + SOLAR_BOX[1]  // 2,
                         SYSTEM_POS[1] - SYSTEM_BOX[1] // 2,
                         active=solar_on)

        x_gap_left  = GRID_POS[0]   + GRID_BOX[0]   // 2
        x_gap_right = SYSTEM_POS[0] - SYSTEM_BOX[0] // 2
        if grid_state == "IMPORT":
            self._arrow_right(draw, x_gap_left, x_gap_right, GRID_POS[1], active=True)
        elif grid_state == "EXPORT":
            self._arrow_left(draw, x_gap_left, x_gap_right, GRID_POS[1], active=True)
        else:
            self._arrow_left(draw, x_gap_left, x_gap_right, GRID_POS[1], active=False)

        self._arrow_right(draw,
                          SYSTEM_POS[0] + SYSTEM_BOX[0] // 2,
                          HOME_POS[0]   - HOME_BOX[0]   // 2,
                          SYSTEM_POS[1],
                          active=load_on)

        y_gap_top = SYSTEM_POS[1] + SYSTEM_BOX[1] // 2
        y_gap_bot = BATT_POS[1]   - BATT_BOX[1]   // 2
        if charging:
            self._arrow_down(draw, BATT_POS[0], y_gap_top, y_gap_bot, active=True)
        else:
            self._arrow_up(draw, BATT_POS[0], y_gap_top, y_gap_bot, active=discharging)

        # ── Boxes ─────────────────────────────────────────────────────────

        self._box(draw, fonts, *SOLAR_POS, *SOLAR_BOX,
                  "SOLAR", f"{int(solar_w)} W",
                  filled=solar_on)

        self._box(draw, fonts, *SYSTEM_POS, *SYSTEM_BOX,
                  "SYSTEM", self._system_label,
                  sub=inverter_state.upper(),
                  filled=True)

        self._box(draw, fonts, *GRID_POS, *GRID_BOX,
                  "GRID", f"{int(abs(grid_w))} W",
                  sub=grid_state,
                  filled=(grid_state == "IMPORT"))
        if grid_state == "LOST":
            bx = GRID_POS[0] + GRID_BOX[0] // 2 - 5
            by = GRID_POS[1] + GRID_BOX[1] // 2 - 5
            r  = 16
            draw.ellipse([bx - r, by - r, bx + r, by + r], fill=BLACK, outline=WHITE, width=2)
            draw.text((bx, by), "\U000F0028", font=fonts["icon"], fill=WHITE, anchor="mm")

        self._box(draw, fonts, *HOME_POS, *HOME_BOX,
                  "HOME", f"{int(load_w)} W")

        batt_sub = "CHARGING" if charging else ("DISCHARGING" if discharging else "IDLE")
        self._box(draw, fonts, *BATT_POS, *BATT_BOX,
                  "BATTERY", f"{int(soc)}%",
                  sub=f"{int(abs(battery_w))} W  ·  {batt_sub}",
                  filled=discharging)
        self._battery_poles(draw, fonts, *BATT_POS, *BATT_BOX)

        return BATT_POS[1] + BATT_BOX[1] // 2 + 8

    # ── Box ───────────────────────────────────────────────────────────────

    def _box(self, draw, fonts, cx, cy, bw, bh, label, value, sub=None, filled=False, icon=None):
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
            draw.text((cx, y0 + 10), icon, font=fonts["icon"], fill=tc, anchor="mt")
        else:
            draw.text((cx, y0 + 10), label, font=fonts["label"], fill=tc, anchor="mt")
        draw.line([(x0 + 8, y0 + 24), (x1 - 8, y0 + 24)], fill=tc, width=1)
        if value is not None:
            draw.text((cx, cy), value, font=fonts["large"], fill=tc, anchor="mm")
        if sub is not None:
            draw.text((cx, y1 - 10), sub, font=fonts["small"], fill=tc, anchor="mb")

    def _battery_poles(self, draw, fonts, cx, cy, bw, bh):
        box_top = cy - bh // 2
        pw, ph  = 20, 12
        offset  = 45
        r       = 3
        for sign, dx in (("+", offset), ("−", -offset)):
            px = cx + dx
            draw.rounded_rectangle(
                [px - pw // 2, box_top - ph, px + pw // 2, box_top + 2],
                radius=r, fill=BLACK, outline=WHITE, width=2)
            draw.text((px, box_top + 14), sign, font=fonts["small"], fill=WHITE, anchor="mm")

    # ── Directional arrows ────────────────────────────────────────────────

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


@_register("section_header")
class SectionHeader(Component):
    def __init__(self, config, hass):
        self._hass  = hass
        self._title = config["title"]
        self._icon  = config.get("icon")

    def render(self, draw, fonts, y):
        return self._hass._render_section_header(draw, fonts, y, self._icon, self._title)


@_register("divider")
class Divider(Component):
    def __init__(self, config, hass):
        self._spacing = config.get("spacing", 10)

    def render(self, draw, fonts, y):
        mid = y + self._spacing // 2
        draw.line([(20, mid), (W - 20, mid)], fill=BLACK, width=1)
        return y + self._spacing


@_register("status_list")
class StatusList(Component):
    def __init__(self, config, hass):
        self._hass  = hass
        self._items = config.get("items", [])

    def entities(self):
        return [item["entity"] for item in self._items]

    def render(self, draw, fonts, y):
        hass = self._hass
        y += 26
        for item in self._items:
            value = self._resolve_value(item["entity"], item.get("value", "state"))
            y = hass._status_row(draw, fonts, y, item["icon"], item["label"], value)
        return y

    def _resolve_value(self, entity, value_type):
        hass = self._hass
        if value_type == "elapsed":
            return hass._elapsed(entity)
        elif value_type == "on_off_elapsed":
            on      = hass.get_state(entity) == "on"
            elapsed = hass._elapsed(entity)
            return f"on · {elapsed}" if on else f"off · {elapsed}"
        elif value_type == "alarm_elapsed":
            alarm   = hass.get_state(entity) == "Alarm"
            elapsed = hass._elapsed(entity)
            return f"for {elapsed}" if alarm else f"OK · {elapsed}"
        else:
            return hass.get_state(entity) or "—"


@_register("energy_strip")
class EnergyStrip(Component):
    def __init__(self, config, hass):
        self._hass   = hass
        sensors      = config.get("sensors", {})
        self._solar  = sensors["solar_today"]
        self._import = sensors["import_daily"]
        self._export = sensors["export_daily"]

    def entities(self):
        return [self._solar, self._import, self._export]

    def render(self, draw, fonts, y):
        hass         = self._hass
        solar_today  = hass._float(self._solar)
        import_today = hass._float(self._import)
        export_today = hass._float(self._export)
        used_today   = max(0.0, import_today - export_today)

        x0, x1, h = 20, 460, 62
        col_w = (x1 - x0) // 4
        hdr_h = 22
        draw.rounded_rectangle([x0, y, x1, y + h], radius=10, fill=WHITE, outline=BLACK, width=2)
        for i, (lbl, val) in enumerate([
            ("SOLAR",  f"{solar_today:.1f} kWh"),
            ("IMPORT", f"{import_today:.1f} kWh"),
            ("EXPORT", f"{export_today:.1f} kWh"),
            ("NET",    f"{used_today:.1f} kWh"),
        ]):
            cx = x0 + col_w * i + col_w // 2
            if i > 0:
                draw.line([(x0 + col_w * i, y + 4), (x0 + col_w * i, y + h - 4)], fill=BLACK, width=1)
            draw.text((cx, y + hdr_h // 2), lbl, font=fonts["label"], fill=BLACK, anchor="mm")
            draw.line([(x0 + col_w * i + 4, y + hdr_h), (x0 + col_w * (i + 1) - 4, y + hdr_h)], fill=BLACK, width=1)
            draw.text((cx, y + hdr_h + (h - hdr_h) // 2), val, font=fonts["medium"], fill=BLACK, anchor="mm")
        return y + h + 22


# ── AppDaemon app ─────────────────────────────────────────────────────────────

class EinkDashboard(hass.Hass):

    def initialize(self):
        self.out_dir   = self.args.get("out_dir",   "/homeassistant/www")
        self.fonts_dir = self.args.get("fonts_dir", "/homeassistant/esphome/apps/dashboard/fonts")
        interval       = self.args.get("render_interval", 60)
        os.makedirs(self.out_dir, exist_ok=True)
        self.fonts = self._load_fonts()

        self.show_timestamp = self.args.get("show_timestamp", True)

        self.pages = []
        for page_cfg in self.args.get("pages", []):
            components = []
            for comp_cfg in page_cfg.get("components", []):
                comp_type = comp_cfg.get("type")
                cls = COMPONENT_REGISTRY.get(comp_type)
                if cls is None:
                    self.log(f"Unknown component type: {comp_type!r}", level="WARNING")
                    continue
                components.append(cls(comp_cfg, self))
            self.pages.append(components)

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
                for idx, components in enumerate(self.pages):
                    self._render_page(idx, components)
        except Exception as e:
            self.log(f"EinkDashboard render error: {e}", level="ERROR")

    def _check_entities(self):
        """Return list of entity IDs that are missing or unavailable."""
        entities = []
        for components in self.pages:
            for comp in components:
                entities += comp.entities()
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

    def _render_page(self, idx, components):
        img  = Image.new("RGB", (W, H), WHITE)
        draw = ImageDraw.Draw(img)
        f    = self.fonts

        y = 0
        for comp in components:
            y = comp.render(draw, f, y)

        if self.show_timestamp:
            from datetime import datetime
            ts = datetime.now().strftime("Updated %Y-%m-%d %H:%M")
            draw.text((W // 2, H - 8), ts, font=f["label"], fill=BLACK, anchor="mb")

        img.save(f"{self.out_dir}/eink_page{idx}.png")
        img_l = img.convert("L")
        img_land_l = img_l.transpose(Image.ROTATE_270)
        img_land_1bit = img_land_l.point(lambda x: 255 if x > 128 else 0, "1")
        with open(f"{self.out_dir}/eink_page{idx}.bin", "wb") as fh:
            fh.write(img_land_1bit.tobytes())
        self.log(f"Rendered eink_page{idx}.png + eink_page{idx}.bin")

    # ── Shared rendering helpers (called by components via hass) ──────────────

    def _render_section_header(self, draw, fonts, y, icon, title):
        if icon:
            icon_w  = draw.textlength(icon, font=fonts["icon"])
            total_w = icon_w + 8 + draw.textlength(title, font=fonts["medium"])
            x = (W - total_w) // 2
            draw.text((x, y), icon, font=fonts["icon"], fill=BLACK, anchor="lm")
            draw.text((x + icon_w + 8, y), title, font=fonts["medium"], fill=BLACK, anchor="lm")
        else:
            x = (W - draw.textlength(title, font=fonts["medium"])) // 2
            draw.text((x, y), title, font=fonts["medium"], fill=BLACK, anchor="lm")
        draw.line([(20, y + 22), (W - 20, y + 22)], fill=BLACK, width=2)
        return y + 22

    def _status_row(self, draw, fonts, y, icon, label, value, margin=20, gap=6):
        iw = draw.textlength(icon, font=fonts["icon_sm"])
        draw.text((margin, y), icon, font=fonts["icon_sm"], fill=BLACK, anchor="lm")
        draw.text((margin + iw + gap, y), f"{label}: {value}", font=fonts["status_text"], fill=BLACK, anchor="lm")
        return y + 32

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

    def _float(self, entity, default=0.0):
        try:
            return float(self.get_state(entity))
        except (ValueError, TypeError):
            return default

    def _load_fonts(self):
        bold = f"{self.fonts_dir}/GothamRnd-Bold.ttf"
        book = f"{self.fonts_dir}/GothamRnd-Book.ttf"
        mdi  = f"{self.fonts_dir}/materialdesignicons-webfont.ttf"
        try:
            return {
                "large":       ImageFont.truetype(bold, 24),
                "medium":      ImageFont.truetype(bold, 22),
                "small":       ImageFont.truetype(book, 13),
                "label":       ImageFont.truetype(book, 12),
                "icon":        ImageFont.truetype(mdi,  28),
                "icon_sm":     ImageFont.truetype(mdi,  22),
                "status_text": ImageFont.truetype(book, 18),
            }
        except Exception as e:
            self.log(f"Font load failed, using default: {e}", level="WARNING")
            d = ImageFont.load_default()
            return {"large": d, "medium": d, "small": d, "label": d, "icon": d, "icon_sm": d, "status_text": d}
