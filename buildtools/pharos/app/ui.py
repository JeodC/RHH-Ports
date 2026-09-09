#!/usr/bin/env python3
"""
Pharos UI
"""
import ctypes
import os
from typing import Optional, Tuple, Any
import collections

import sdl2
import sdl2.sdlttf as ttf
import sdl2.sdlimage as img

from config import color_btn_a, color_btn_b

# ----------------------------------------------------------------------
# Colors
# ----------------------------------------------------------------------
color_row_bg = "#383838"
color_row_muted = "#2a2a2a"
color_menu_bg = "#141414"
color_footer_bg = "#333333"
color_progress_bar = "#00b400"
color_text = "#ffffff"

# ----------------------------------------------------------------------
# Hex to SDL_Color
# ----------------------------------------------------------------------
def hex_to_sdl(hex_str: str) -> sdl2.SDL_Color:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        return sdl2.SDL_Color(255, 255, 255, 255)
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return sdl2.SDL_Color(r, g, b, 255)
    except ValueError:
        return sdl2.SDL_Color(255, 255, 255, 255)

# Preconvert common colors
c_row_bg = hex_to_sdl(color_row_bg)
c_row_muted = hex_to_sdl(color_row_muted)
c_row_sel = hex_to_sdl(color_btn_a)
c_menu_bg = hex_to_sdl(color_menu_bg)
c_footer_bg = hex_to_sdl(color_footer_bg)
c_progress_bar = hex_to_sdl(color_progress_bar)
c_text = hex_to_sdl(color_text)
c_btn_a = hex_to_sdl(color_btn_a)
c_btn_b = hex_to_sdl(color_btn_b)

from config import BASE_PATH
FONT_PATH = os.path.join(BASE_PATH, "fonts", "romm.ttf")
FONT_SIZE = 12
HEADER_HEIGHT = 25
FOOTER_HEIGHT = 20
BODY_MARGIN_TOP = 0
BUTTON_AREA_HEIGHT = 50
MAX_TEXTURE_CACHE = 48

# Reserved height for the store-icon row above the button area; 0 if no store data.
STORE_ROW_HEIGHT = 36

# port.json store name -> icon filename in resources/stores/
# (populated by buildtools/pharos/download_store_icons.py).
STORE_ICON_FILES = {
    "Steam":        "steam.png",
    "GOG":          "gog.png",
    "Itch.io":      "itch.png",
    "Epic Games":   "epic.png",
    "Humble Store": "humble.png",
    "Fanatical":    "fanatical.png",
}
STORE_ICONS_DIR = os.path.join(BASE_PATH, "resources", "stores")
STORE_ICON_SIZE = 24
# Steam discount green.
c_discount_text = sdl2.SDL_Color(190, 238, 17, 255)

# ----------------------------------------------------------------------
# UserInterface
# ----------------------------------------------------------------------
class UserInterface:
    _instance = None

    screen_width = 640
    screen_height = 480

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # idempotent init
        if getattr(self, "_initialized", False):
            return

        # Track what this instance initialized so cleanup only tears down its own.
        # main.py already inited SDL_INIT_VIDEO, so we never touch it.
        self._inited_ttf = False
        self._inited_img_flags = 0

        # --- SDL_image init: ensure PNG/JPG available ---
        desired_img_flags = img.IMG_INIT_PNG | img.IMG_INIT_JPG
        current_img = img.IMG_Init(0)
        if (current_img & desired_img_flags) != desired_img_flags:
            got = img.IMG_Init(desired_img_flags)
            if (got & desired_img_flags) != desired_img_flags:
                raise RuntimeError("Failed to init SDL_image for PNG/JPG")
            self._inited_img_flags = got & desired_img_flags

        # --- SDL_ttf init ---
        try:
            if ttf.TTF_WasInit() == 0:
                if ttf.TTF_Init() != 0:
                    raise RuntimeError("TTF_Init failed")
                self._inited_ttf = True
        except Exception:
            # Some SDL2 wrappers expose TTF_WasInit differently; attempt init anyway
            try:
                ttf.TTF_Init()
                self._inited_ttf = True
            except Exception:
                # Non-fatal: continue fontless, text drawing is skipped.
                self._inited_ttf = False

        # --- Create window, renderer, and render target texture ---
        self.window = self._create_window()
        self.renderer = self._create_renderer()

        # Render-target texture used as the main drawing surface.
        self.screen_texture = sdl2.SDL_CreateTexture(
            self.renderer,
            sdl2.SDL_PIXELFORMAT_RGBA8888,
            sdl2.SDL_TEXTUREACCESS_TARGET,
            self.screen_width,
            self.screen_height
        )
        if not self.screen_texture:
            raise RuntimeError("Failed to create render target texture")

        self.font = None
        if self._inited_ttf:
            try:
                self.font = ttf.TTF_OpenFont(FONT_PATH.encode(), FONT_SIZE)
                if not self.font:
                    print("[UI] Warning: failed to load font.")
            except Exception:
                self.font = None
                print("[UI] Warning: exception opening font.")

        self.draw_clear()

        self._scroll_speed = 1
        self._row_scroll_state = {}
        self._desc_scroll_state = {}
        self._scroll_start_delay = 60
        self._scroll_end_delay = 60

        # LRU texture cache: path -> texture
        self.texture_cache = collections.OrderedDict()
        self._initialized = True

    # ------------------------------------------------------------------
    # SDL2 setup helpers
    # ------------------------------------------------------------------
    def _create_window(self):
        window = sdl2.SDL_CreateWindow(
            b"Pharos",
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            0, 0,
            sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_SHOWN,
        )
        if not window:
            raise RuntimeError(f"SDL_CreateWindow failed: {sdl2.SDL_GetError().decode()}")
        return window

    def _create_renderer(self):
        renderer = sdl2.SDL_CreateRenderer(
            self.window, -1, sdl2.SDL_RENDERER_ACCELERATED
        )
        if not renderer:
            raise RuntimeError(f"SDL_CreateRenderer failed: {sdl2.SDL_GetError().decode()}")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"0")
        return renderer

    # ------------------------------------------------------------------
    # Frame management
    # ------------------------------------------------------------------
    def draw_start(self):
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
        sdl2.SDL_RenderClear(self.renderer)
        sdl2.SDL_SetRenderTarget(self.renderer, self.screen_texture)
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
        sdl2.SDL_RenderClear(self.renderer)

    def draw_clear(self):
        sdl2.SDL_SetRenderDrawColor(self.renderer, 0, 0, 0, 255)
        sdl2.SDL_RenderClear(self.renderer)

    def render_to_screen(self):
        sdl2.SDL_SetRenderTarget(self.renderer, None)
        w = ctypes.c_int()
        h = ctypes.c_int()
        sdl2.SDL_GetWindowSize(self.window, ctypes.byref(w), ctypes.byref(h))
        dst_rect = sdl2.SDL_Rect(0, 0, w.value, h.value)
        sdl2.SDL_RenderCopy(self.renderer, self.screen_texture, None, dst_rect)
        sdl2.SDL_RenderPresent(self.renderer)
        sdl2.SDL_SetRenderTarget(self.renderer, self.screen_texture)

    # ------------------------------------------------------------------
    # Cleanup Does NOT call SDL_Quit().
    # Top-level code should call SDL_Quit() once for the process.
    # ------------------------------------------------------------------
    def cleanup(self):
        for tex in list(self.texture_cache.values()):
            try:
                sdl2.SDL_DestroyTexture(tex)
            except Exception:
                pass
        self.texture_cache.clear()

        try:
            if getattr(self, "screen_texture", None):
                sdl2.SDL_DestroyTexture(self.screen_texture)
                self.screen_texture = None
        except Exception:
            pass

        try:
            if getattr(self, "renderer", None):
                sdl2.SDL_DestroyRenderer(self.renderer)
                self.renderer = None
        except Exception:
            pass

        try:
            if getattr(self, "window", None):
                sdl2.SDL_DestroyWindow(self.window)
                self.window = None
        except Exception:
            pass

        try:
            if getattr(self, "font", None):
                ttf.TTF_CloseFont(self.font)
                self.font = None
        except Exception:
            pass

        # Quit TTF/IMG only if we inited them; other owners manage their own lifetime.
        try:
            if self._inited_img_flags:
                img.IMG_Quit()
                self._inited_img_flags = 0
        except Exception:
            pass

        try:
            if self._inited_ttf:
                ttf.TTF_Quit()
                self._inited_ttf = False
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Text rendering helpers
    # ------------------------------------------------------------------
    def _render_text(self, text: str, color: sdl2.SDL_Color):
        if not getattr(self, "font", None):
            return None
        try:
            return ttf.TTF_RenderUTF8_Blended(self.font, text.encode("utf-8"), color)
        except Exception:
            return None

    def _blit_text(self, surface: Any, x: int, y: int):
        if not surface:
            return
        texture = None
        try:
            texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
            if not texture:
                return
            w = ctypes.c_int()
            h = ctypes.c_int()
            sdl2.SDL_QueryTexture(texture, None, None, ctypes.byref(w), ctypes.byref(h))
            dst = sdl2.SDL_Rect(x, y, w.value, h.value)
            sdl2.SDL_RenderCopy(self.renderer, texture, None, dst)
        finally:
            try:
                if texture:
                    sdl2.SDL_DestroyTexture(texture)
            except Exception:
                pass
            try:
                sdl2.SDL_FreeSurface(surface)
            except Exception:
                pass

    def draw_text(self, pos: Tuple[int, int], text: str, color: sdl2.SDL_Color = c_text):
        if isinstance(color, str):
            color = hex_to_sdl(color)
        surface = self._render_text(text, color)
        self._blit_text(surface, pos[0], pos[1])

    # ------------------------------------------------------------------
    # Shapes
    # ------------------------------------------------------------------
    def draw_rectangle(self, rect: Tuple[int, int, int, int], fill: Optional[sdl2.SDL_Color] = None):
        if fill:
            if isinstance(fill, str):
                fill = hex_to_sdl(fill)
            sdl2.SDL_SetRenderDrawColor(self.renderer, fill.r, fill.g, fill.b, fill.a)
            sdl2.SDL_RenderFillRect(self.renderer, sdl2.SDL_Rect(*rect))

    def draw_rectangle_outline(self, rect: Tuple[int, int, int, int], color: sdl2.SDL_Color, width: int = 1):
        if isinstance(color, str):
            color = hex_to_sdl(color)
        sdl2.SDL_SetRenderDrawColor(self.renderer, color.r, color.g, color.b, color.a)
        for i in range(width):
            outer = sdl2.SDL_Rect(rect[0] - i, rect[1] - i, rect[2] + 2 * i, rect[3] + 2 * i)
            sdl2.SDL_RenderDrawRect(self.renderer, outer)

    def draw_circle(self, center: Tuple[int, int], radius: int, fill: Optional[sdl2.SDL_Color] = None):
        if fill:
            if isinstance(fill, str):
                fill = hex_to_sdl(fill)
            sdl2.SDL_SetRenderDrawColor(self.renderer, fill.r, fill.g, fill.b, fill.a)
            for dy in range(-radius, radius + 1):
                dx = int((radius ** 2 - dy ** 2) ** 0.5)
                sdl2.SDL_RenderDrawLine(
                    self.renderer,
                    center[0] - dx, center[1] + dy,
                    center[0] + dx, center[1] + dy
                )

    def draw_rectangle_r(self, rect, radius, fill=None, outline=None):
        x, y, w, h = map(int, rect)
        if fill:
            self.draw_rectangle((x+radius, y+radius, w-2*radius, h-2*radius), fill)
            self.draw_rectangle((x+radius, y, w-2*radius, radius), fill)
            self.draw_rectangle((x+radius, y+h-radius, w-2*radius, radius), fill)
            self.draw_rectangle((x, y+radius, radius, h-2*radius), fill)
            self.draw_rectangle((x+w-radius, y+radius, radius, h-2*radius), fill)
            self.draw_circle((x+radius, y+radius), radius, fill)
            self.draw_circle((x+w-radius, y+radius), radius, fill)
            self.draw_circle((x+radius, y+h-radius), radius, fill)
            self.draw_circle((x+w-radius, y+h-radius), radius, fill)
        if outline:
            self.draw_rectangle_outline((x, y, w, h), outline)

    # ------------------------------------------------------------------
    # UI Components
    # ------------------------------------------------------------------
    def row_list(self, text: str, pos: Tuple[float, float], width: int, height: int,
                 selected: bool = False, fill: Optional[sdl2.SDL_Color] = None,
                 color: sdl2.SDL_Color = c_text, outline: Optional[sdl2.SDL_Color] = None,
                 highlight: bool = False):
        if highlight and not selected:
            bg = hex_to_sdl("#d3b948")
        else:
            bg = c_row_sel if selected else (fill if fill else c_row_bg)
        self.draw_rectangle((int(pos[0]), int(pos[1]), width, height), fill=bg)
        clip_rect = sdl2.SDL_Rect(int(pos[0]), int(pos[1]), width, height)
        sdl2.SDL_RenderSetClipRect(self.renderer, clip_rect)
        text_w = self.get_text_width(text)
        if text_w <= width - 20:
            self.draw_text((int(pos[0] + 12), int(pos[1] + 8)), text, color)
            if text in self._row_scroll_state:
                self._row_scroll_state[text]["offset"] = 0
                self._row_scroll_state[text]["timer"] = self._scroll_start_delay
        else:
            state = self._row_scroll_state.get(text, {"offset": 0, "direction": 1, "timer": self._scroll_start_delay})
            if state["timer"] > 0:
                state["timer"] -= 1
            else:
                state["offset"] += state["direction"] * self._scroll_speed
                max_offset = text_w - (width - 20)
                if state["offset"] >= max_offset:
                    state["offset"] = max_offset
                    state["direction"] = -1
                    state["timer"] = self._scroll_end_delay
                elif state["offset"] <= 0:
                    state["offset"] = 0
                    state["direction"] = 1
                    state["timer"] = self._scroll_start_delay
            self._row_scroll_state[text] = state
            self.draw_text((int(pos[0] + 12 - state["offset"]), int(pos[1] + 8)), text, color)
        sdl2.SDL_RenderSetClipRect(self.renderer, None)

    def button_circle(self, pos: Tuple[float, float], button: str, label: str,
                      color: Optional[sdl2.SDL_Color] = None):
        if color is None:
            color = c_btn_a
        radius = 8
        padding = 8
        self.draw_circle((int(pos[0]), int(pos[1])), radius, fill=color)
        btn_w = self.get_text_width(button)
        text_x = int(pos[0] - btn_w // 2)
        text_y = int(pos[1] - FONT_SIZE // 2)
        self.draw_text((text_x, text_y), button, c_text)
        label_x = int(pos[0] + radius + padding)
        self.draw_text((label_x, text_y), label, c_text)

    def get_text_width(self, text: str) -> int:
        if not getattr(self, "font", None):
            return 0
        w = ctypes.c_int()
        h = ctypes.c_int()
        try:
            ttf.TTF_SizeUTF8(self.font, text.encode("utf-8"), ctypes.byref(w), ctypes.byref(h))
            return w.value
        except Exception:
            return 0

    def draw_log(self, text: str = "",
                 text_color: str = color_text, background: bool = True):
        y = self.screen_height - FOOTER_HEIGHT
        self.draw_rectangle((0, y, self.screen_width, FOOTER_HEIGHT), fill=c_footer_bg)
        text_color_sdl = hex_to_sdl(text_color)
        self.draw_text((10, y + 3), text, text_color_sdl)

    def draw_loader(self, percent: int):
        if percent < 0:
            return
        color_sdl = c_progress_bar
        margin = 10
        radius = 2
        loader_height = 6
        y_start = self.screen_height - FOOTER_HEIGHT - loader_height
        filled_width = int((self.screen_width - 2 * margin) * (percent / 100))
        if filled_width < 1:
            filled_width = 1
        self.draw_rectangle_r(
            [margin, y_start, filled_width, loader_height],
            radius, fill=color_sdl, outline=None
        )

    def draw_header(self, title: str, color: str = color_text):
        color_sdl = hex_to_sdl(color)
        self.draw_rectangle((0, 0, self.screen_width, HEADER_HEIGHT), fill=c_menu_bg)
        self.draw_text((self.screen_width // 2 - self.get_text_width(title)//2, 8), title, color_sdl)

    # ------------------------------------------------------------------
    # Image loading with LRU cache
    # ------------------------------------------------------------------
    def _cache_texture(self, path: str, texture: Any):
        # Evict oldest if full
        if path in self.texture_cache:
            # move to end (most recently used)
            self.texture_cache.move_to_end(path)
            return
        while len(self.texture_cache) >= MAX_TEXTURE_CACHE:
            old_path, old_tex = self.texture_cache.popitem(last=False)
            try:
                sdl2.SDL_DestroyTexture(old_tex)
            except Exception:
                pass
        self.texture_cache[path] = texture

    def draw_port_image(self, port: Any, max_w: int = 380, max_h: int = 280) -> None:
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"2")

        path = getattr(port, "image_path", None)
        if not path or not os.path.exists(path):
            return

        texture = self.texture_cache.get(path)
        if texture is None:
            surface = None
            texture = None
            try:
                surface = img.IMG_Load(path.encode())
                if not surface:
                    return
                texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
                if not texture:
                    return
                self._cache_texture(path, texture)
            except Exception:
                # drop any half-created texture on failure
                try:
                    if texture:
                        sdl2.SDL_DestroyTexture(texture)
                except Exception:
                    pass
                return
            finally:
                try:
                    if surface:
                        sdl2.SDL_FreeSurface(surface)
                except Exception:
                    pass

        w = ctypes.c_int()
        h = ctypes.c_int()
        sdl2.SDL_QueryTexture(texture, None, None, ctypes.byref(w), ctypes.byref(h))
        tex_w, tex_h = w.value, h.value
        if tex_w == 0 or tex_h == 0:
            return

        # Anchor on the same center as the description text; clamp max_w
        # symmetrically so the image stays on-screen on both sides.
        desc_center_x = self.screen_width * 3 // 4 - 20
        right_margin = 10
        left_margin = 10
        max_half = min(desc_center_x - left_margin,
                       self.screen_width - right_margin - desc_center_x)
        max_w = min(max_w, 2 * max_half)

        scale = min(max_w / tex_w, max_h / tex_h, 1.0)
        dw, dh = int(tex_w * scale), int(tex_h * scale)

        x = desc_center_x - dw // 2
        y = 40 + (max_h - dh) // 2

        dst_rect = sdl2.SDL_Rect(x, y, dw, dh)
        sdl2.SDL_RenderCopyEx(self.renderer, texture, None, dst_rect, 0, None, sdl2.SDL_FLIP_NONE)

    def draw_wrapped_text_centered(self, text: str, center_x: int, start_y: int,
                                   max_width: int, color: sdl2.SDL_Color = c_text,
                                   line_spacing: int = 2, reserve_bottom: int = 0):

        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            if self.get_text_width(test_line) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        line_height = FONT_SIZE + line_spacing
        text_height = len(lines) * line_height

        desc_top_y = start_y
        desc_bottom_y = self.screen_height - FOOTER_HEIGHT - BUTTON_AREA_HEIGHT - reserve_bottom
        max_area_height = desc_bottom_y - desc_top_y

        if text_height > max_area_height:
            state = self._desc_scroll_state.get(text, {"offset": 0, "direction": 1, "timer": self._scroll_start_delay})
            if state["timer"] > 0:
                state["timer"] -= 1
            else:
                state["offset"] += state["direction"] * self._scroll_speed
                max_offset = text_height - max_area_height
                if state["offset"] >= max_offset:
                    state["offset"] = max_offset
                    state["direction"] = -1
                    state["timer"] = self._scroll_end_delay
                elif state["offset"] <= 0:
                    state["offset"] = 0
                    state["direction"] = 1
                    state["timer"] = self._scroll_start_delay
            self._desc_scroll_state[text] = state
            offset = state["offset"]
        else:
            offset = 0
            if text in self._desc_scroll_state:
                del self._desc_scroll_state[text]

        for i, line in enumerate(lines):
            line_width = self.get_text_width(line)
            desc_x = center_x - line_width // 2
            desc_y = desc_top_y + i * line_height - offset
            if desc_top_y <= desc_y <= desc_bottom_y - line_height:
                self.draw_text((desc_x, desc_y), line, color)

    def _load_store_texture(self, name: str):
        filename = STORE_ICON_FILES.get(name)
        if not filename:
            return None
        path = os.path.join(STORE_ICONS_DIR, filename)
        if not os.path.exists(path):
            return None
        texture = self.texture_cache.get(path)
        if texture is not None:
            return texture
        surface = img.IMG_Load(path.encode())
        if not surface:
            return None
        try:
            texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
            if not texture:
                return None
            self._cache_texture(path, texture)
            return texture
        finally:
            try:
                sdl2.SDL_FreeSurface(surface)
            except Exception:
                pass

    def draw_port_stores(self, stores, discount_lookup, center_x: int,
                         max_width: int, bottom_y: int):
        """Render the store-icon row for a port.

        discount_lookup: callable(store_name) -> discount percent (0/None if none).
        bottom_y: y of the bottom edge of the reserved area.
        """
        if not stores:
            return

        # Build a list of (texture, discount_text, total_width) per entry.
        gap_after_icon = 4         # px between icon and discount text (if shown)
        gap_between_items = 12     # px between entries
        entries = []
        for s in stores:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "")
            tex = self._load_store_texture(name)
            if tex is None:
                continue
            cut = discount_lookup(name) if discount_lookup else 0
            disc_text = f"-{cut}%" if cut and cut > 0 else ""
            disc_w = self.get_text_width(disc_text) if disc_text else 0
            entry_w = STORE_ICON_SIZE + (gap_after_icon + disc_w if disc_text else 0)
            entries.append((tex, disc_text, entry_w))

        if not entries:
            return

        total_w = sum(e[2] for e in entries) + gap_between_items * (len(entries) - 1)
        # Clip / right-align if overflow
        if total_w > max_width:
            total_w = max_width
        x = center_x - total_w // 2
        y_icon = bottom_y - STORE_ICON_SIZE - 4  # 4px margin above button area
        y_text = y_icon + (STORE_ICON_SIZE - FONT_SIZE) // 2

        for tex, disc_text, entry_w in entries:
            dst = sdl2.SDL_Rect(x, y_icon, STORE_ICON_SIZE, STORE_ICON_SIZE)
            sdl2.SDL_RenderCopy(self.renderer, tex, None, dst)
            if disc_text:
                self.draw_text(
                    (x + STORE_ICON_SIZE + gap_after_icon, y_text),
                    disc_text,
                    c_discount_text,
                )
            x += entry_w + gap_between_items
