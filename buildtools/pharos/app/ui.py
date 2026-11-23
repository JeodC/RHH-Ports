#!/usr/bin/env python3
"""
Pharos UI
"""

import ctypes
import functools
import math
import os
from typing import Tuple
import collections
from contextlib import suppress

import sdl2
import sdl2.sdlttf as ttf
import sdl2.sdlimage as img

from config import BASE_PATH
from theme import theme


# ----------------------------------------------------------------------
# Hex to SDL_Color
# ----------------------------------------------------------------------
@functools.lru_cache(maxsize=256)
def hex_to_sdl(hex_str: str) -> sdl2.SDL_Color:
    return sdl2.SDL_Color(*bytes.fromhex(hex_str[1:]), 255)


FONT_PATH = os.path.join(BASE_PATH, "fonts", "wqy-microhei-mono.ttf")
FONT_SIZE = 12
HEADER_HEIGHT = 25
FOOTER_HEIGHT = 20
BUTTON_AREA_HEIGHT = 50
BUTTON_PADDING = 8
MAX_TEXTURE_CACHE = 16
MAX_TEXT_CACHE = 256
FONT_RISE = 0.1  # of the font size, text is drawn this much higher
LETTER_WIDTH = 1229 / 2048  # of the font size
MAX_FONT_SIZE = 20  # fits a row and the button bar

# Reserved height for the store-icon row above the button area; 0 if no store data.
STORE_ROW_HEIGHT = 36

# port.json store name -> icon filename in resources/stores/
# (populated by buildtools/pharos/download_store_icons.py).
STORE_ICON_FILES = {
    "Steam": "steam.png",
    "GOG": "gog.png",
    "Itch.io": "itch.png",
    "Epic Games": "epic.png",
    "Humble Store": "humble.png",
    "Fanatical": "fanatical.png",
}
STORE_ICONS_DIR = os.path.join(BASE_PATH, "resources", "stores")
STORE_ICON_SIZE = 24


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

        # The layout is always 640x480. Small screens shrink it, others draw it at their resolution.
        w, h = self.window_size()
        scale = min(w / self.screen_width, h / self.screen_height, 1.0)
        self.scale_x, self.scale_y = (w / self.screen_width, h / self.screen_height) if scale == 1 else (1.0, 1.0)
        self.font_size = min(round(FONT_SIZE / scale), MAX_FONT_SIZE)
        self.footer_height = FOOTER_HEIGHT + self.font_size - FONT_SIZE
        self.desc_shift = 5 * (self.font_size - FONT_SIZE)
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"1" if scale < 1 else b"0")

        # Render-target texture used as the main drawing surface.
        self.screen_texture = sdl2.SDL_CreateTexture(
            self.renderer,
            sdl2.SDL_PIXELFORMAT_RGBA8888,
            sdl2.SDL_TEXTUREACCESS_TARGET,
            round(self.screen_width * self.scale_x),
            round(self.screen_height * self.scale_y),
        )
        if not self.screen_texture:
            raise RuntimeError("Failed to create render target texture")
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"2")

        self.font = self._draw_font = None
        if self._inited_ttf:
            try:
                self.font = ttf.TTF_OpenFont(FONT_PATH.encode(), self.font_size)
                if self.font:
                    self._draw_font = self._open_draw_font()
                else:
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

        # LRU texture caches: path -> texture, (text, color) -> (texture, h)
        self.texture_cache = collections.OrderedDict()
        self._text_cache = collections.OrderedDict()
        self._initialized = True

    # ------------------------------------------------------------------
    # SDL2 setup helpers
    # ------------------------------------------------------------------
    def _create_window(self):
        window = sdl2.SDL_CreateWindow(
            b"Pharos",
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            sdl2.SDL_WINDOWPOS_UNDEFINED,
            0,
            0,
            sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP | sdl2.SDL_WINDOW_SHOWN,
        )
        if not window:
            raise RuntimeError(f"SDL_CreateWindow failed: {sdl2.SDL_GetError().decode()}")
        return window

    def _create_renderer(self):
        renderer = sdl2.SDL_CreateRenderer(self.window, -1, sdl2.SDL_RENDERER_ACCELERATED)
        if not renderer:
            raise RuntimeError(f"SDL_CreateRenderer failed: {sdl2.SDL_GetError().decode()}")
        return renderer

    def _open_draw_font(self):
        if self.scale_x == self.scale_y == 1:
            return self.font
        path = FONT_PATH.encode()
        # Needs SDL_ttf 2.0.18, draw_text stretches the letters without it
        with suppress(Exception):
            # Rounding per letter would make lines longer than on the canvas
            dpi_x = 72 * self.scale_x * self._letter_width(self.font) / (self.font_size * LETTER_WIDTH)
            if font := ttf.TTF_OpenFontDPI(path, self.font_size, round(dpi_x), round(72 * self.scale_y)):
                return font
        return ttf.TTF_OpenFont(path, round(self.font_size * self.scale_y))

    @staticmethod
    def _letter_width(font) -> int:
        w = ctypes.c_int()
        ttf.TTF_SizeUTF8(font, b"M", ctypes.byref(w), None)
        return w.value

    def window_size(self) -> Tuple[int, int]:
        w = ctypes.c_int()
        h = ctypes.c_int()
        sdl2.SDL_GetWindowSize(self.window, ctypes.byref(w), ctypes.byref(h))
        return w.value, h.value

    def refresh_rate(self) -> int:
        mode = sdl2.SDL_DisplayMode()
        sdl2.SDL_GetCurrentDisplayMode(max(0, sdl2.SDL_GetWindowDisplayIndex(self.window)), ctypes.byref(mode))
        return mode.refresh_rate

    # ------------------------------------------------------------------
    # Frame management
    # ------------------------------------------------------------------
    def draw_start(self):
        self._target_canvas()
        self.draw_clear()

    def _target_canvas(self):
        sdl2.SDL_SetRenderTarget(self.renderer, self.screen_texture)
        self._use_scale(True)

    def _use_scale(self, on: bool):
        sdl2.SDL_RenderSetScale(self.renderer, self.scale_x if on else 1, self.scale_y if on else 1)

    def draw_clear(self):
        background = hex_to_sdl(theme.background)
        sdl2.SDL_SetRenderDrawColor(self.renderer, background.r, background.g, background.b, 255)
        sdl2.SDL_RenderClear(self.renderer)

    def render_to_screen(self):
        sdl2.SDL_SetRenderTarget(self.renderer, None)
        dst_rect = sdl2.SDL_Rect(0, 0, *self.window_size())
        sdl2.SDL_RenderCopy(self.renderer, self.screen_texture, None, dst_rect)
        sdl2.SDL_RenderPresent(self.renderer)
        self._target_canvas()

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
        for tex, _ in self._text_cache.values():
            sdl2.SDL_DestroyTexture(tex)
        self._text_cache.clear()

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
                if self._draw_font != self.font:
                    ttf.TTF_CloseFont(self._draw_font)
                ttf.TTF_CloseFont(self.font)
                self.font = self._draw_font = None
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
            return ttf.TTF_RenderUTF8_Blended(self._draw_font, text.encode("utf-8"), color)
        except Exception:
            return None

    def _text_texture(self, text: str, color: sdl2.SDL_Color):
        key = (text, color.r, color.g, color.b)
        cached = self._text_cache.get(key)
        if cached:
            self._text_cache.move_to_end(key)
            return cached
        surface = self._render_text(text, color)
        if not surface:
            return None
        try:
            texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
            if not texture:
                return None
            cached = (texture, surface.contents.h)
        finally:
            sdl2.SDL_FreeSurface(surface)
        if len(self._text_cache) >= MAX_TEXT_CACHE:
            sdl2.SDL_DestroyTexture(self._text_cache.popitem(last=False)[1][0])
        self._text_cache[key] = cached
        return cached

    def draw_text(self, pos: Tuple[int, int], text: str, color: str = ""):
        cached = self._text_texture(text, hex_to_sdl(color or theme.text))
        if cached:
            texture, h = cached
            w = round(self.get_text_width(text) * self.scale_x)
            x = round(pos[0] * self.scale_x)
            y = round(pos[1] * self.scale_y) - round(self.font_size * self.scale_y * FONT_RISE)
            self._use_scale(False)
            sdl2.SDL_RenderCopy(self.renderer, texture, None, sdl2.SDL_Rect(x, y, w, h))
            self._use_scale(True)

    # ------------------------------------------------------------------
    # Shapes
    # ------------------------------------------------------------------
    def draw_rectangle(self, rect: Tuple[int, int, int, int], fill: str = ""):
        if fill:
            color = hex_to_sdl(fill)
            sdl2.SDL_SetRenderDrawColor(self.renderer, color.r, color.g, color.b, color.a)
            sdl2.SDL_RenderFillRect(self.renderer, sdl2.SDL_Rect(*rect))

    def draw_circle(self, center: Tuple[int, int], radius: int, fill: str = ""):
        if fill:
            color = hex_to_sdl(fill)
            sdl2.SDL_SetRenderDrawColor(self.renderer, color.r, color.g, color.b, color.a)
            x, y = round(center[0] * self.scale_x), round(center[1] * self.scale_y)
            radius_y = round(radius * self.scale_y)
            self._use_scale(False)
            for dy in range(-radius_y, radius_y + 1):
                dx = int(radius * self.scale_x / radius_y * math.sqrt(radius_y**2 - dy**2))
                sdl2.SDL_RenderDrawLine(self.renderer, x - dx, y + dy, x + dx, y + dy)
            self._use_scale(True)

    def draw_rectangle_r(self, rect, radius, fill: str = ""):
        x, y, w, h = map(int, rect)
        if fill:
            self.draw_rectangle((x + radius, y + radius, w - 2 * radius, h - 2 * radius), fill)
            self.draw_rectangle((x + radius, y, w - 2 * radius, radius), fill)
            self.draw_rectangle((x + radius, y + h - radius, w - 2 * radius, radius), fill)
            self.draw_rectangle((x, y + radius, radius, h - 2 * radius), fill)
            self.draw_rectangle((x + w - radius, y + radius, radius, h - 2 * radius), fill)
            self.draw_circle((x + radius, y + radius), radius, fill)
            self.draw_circle((x + w - radius, y + radius), radius, fill)
            self.draw_circle((x + radius, y + h - radius), radius, fill)
            self.draw_circle((x + w - radius, y + h - radius), radius, fill)

    # ------------------------------------------------------------------
    # UI Components
    # ------------------------------------------------------------------
    def _scroll_offset(self, states: dict, text: str, max_offset: int) -> int:
        if max_offset <= 0:
            states.pop(text, None)
            return 0
        state = states.setdefault(text, {"offset": 0, "direction": 1, "timer": self._scroll_start_delay})
        if state["timer"] > 0:
            state["timer"] -= 1
        else:
            state["offset"] += state["direction"] * self._scroll_speed
            if state["offset"] >= max_offset:
                state.update(offset=max_offset, direction=-1, timer=self._scroll_end_delay)
            elif state["offset"] <= 0:
                state.update(offset=0, direction=1, timer=self._scroll_start_delay)
        return state["offset"]

    def row_list(
        self,
        text: str,
        pos: Tuple[float, float],
        width: int,
        height: int,
        selected: bool = False,
        highlight: bool = False,
        muted: bool = False,
    ):
        if selected:
            bg, color = theme.row_selected, theme.row_selected_text
        elif highlight:
            bg, color = theme.row_highlight, theme.row_highlight_text
        else:
            bg, color = theme.row_muted if muted else theme.row_bg, theme.row_text
        self.draw_rectangle((int(pos[0]), int(pos[1]), width, height), fill=bg)
        clip_rect = sdl2.SDL_Rect(int(pos[0]), int(pos[1]), width, height)
        sdl2.SDL_RenderSetClipRect(self.renderer, clip_rect)
        text_w = self.get_text_width(text)
        text_y = int(pos[1] + (height - self.font_size) // 2)
        offset = self._scroll_offset(self._row_scroll_state, text, text_w - (width - 20))
        self.draw_text((int(pos[0] + 12 - offset), text_y), text, color)
        sdl2.SDL_RenderSetClipRect(self.renderer, None)

    def button_circle(self, pos: Tuple[float, float], button: str, label: str, color: str) -> float:
        """Returns the x where the label ends"""
        radius, stretch = self._button_size(button)
        x, y = int(pos[0]) + stretch, int(pos[1])
        self.draw_circle((x - stretch, y), radius, fill=color)
        if stretch:
            self.draw_circle((x + stretch, y), radius, fill=color)
            self.draw_rectangle((x - stretch, y - radius, 2 * stretch, 2 * radius + 1), fill=color)
        text_y = y - self.font_size // 2
        self.draw_text((x - self.get_text_width(button) // 2, text_y), button, theme.btn_text)
        self.draw_text((x + stretch + radius + BUTTON_PADDING, text_y), label)
        return pos[0] + self.button_width(button, label)

    def button_width(self, button: str, label: str) -> int:
        radius, stretch = self._button_size(button)
        return 2 * stretch + radius + BUTTON_PADDING + self.get_text_width(label)

    def _button_size(self, button: str) -> Tuple[int, int]:
        radius = max(8, self.font_size // 2 + 2)
        # Wider for a two-letter name
        return radius, max(0, (self.get_text_width(button) + 8) // 2 - radius)

    @functools.lru_cache(maxsize=2048)
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

    def draw_log(self, text: str = ""):
        y = self.screen_height - self.footer_height
        self.draw_rectangle((0, y, self.screen_width, self.footer_height), fill=theme.footer_bg)
        self.draw_text((10, y + 3), text, theme.footer_text)

    def draw_loader(self, percent: int):
        if percent < 0:
            return
        margin = 10
        radius = 2
        loader_height = 6
        y_start = self.screen_height - self.footer_height - loader_height
        filled_width = int((self.screen_width - 2 * margin) * (percent / 100))
        if filled_width < 1:
            filled_width = 1
        self.draw_rectangle_r([margin, y_start, filled_width, loader_height], radius, fill=theme.progress_bar)

    def draw_header(self, title: str, info: str = ""):
        self.draw_rectangle((0, 0, self.screen_width, HEADER_HEIGHT), fill=theme.header_bg)
        y = max(2, 8 - (self.font_size - FONT_SIZE))
        title_w = self.get_text_width(title)
        title_x = self.screen_width // 2 - title_w // 2
        info_x = self.screen_width - 10 - self.get_text_width(info)
        # Long titles shift left for the info
        shifted_x = min(title_x, info_x - 20 - title_w)
        if info and shifted_x >= 10:
            title_x = shifted_x
            self.draw_text((info_x, y), info, theme.header_info)
        self.draw_text((title_x, y), title, theme.header_text)

    # ------------------------------------------------------------------
    # Image loading with LRU cache
    # ------------------------------------------------------------------
    def _load_texture(self, path: str):
        texture = self.texture_cache.get(path)
        if texture is not None:
            # move to end (most recently used)
            self.texture_cache.move_to_end(path)
            return texture
        surface = img.IMG_Load(path.encode())
        if not surface:
            return None
        texture = sdl2.SDL_CreateTextureFromSurface(self.renderer, surface)
        sdl2.SDL_FreeSurface(surface)
        if not texture:
            return None
        # Evict oldest if full
        while len(self.texture_cache) >= MAX_TEXTURE_CACHE:
            sdl2.SDL_DestroyTexture(self.texture_cache.popitem(last=False)[1])
        self.texture_cache[path] = texture
        return texture

    def has_texture(self, path: str) -> bool:
        return path in self.texture_cache

    def draw_port_image(self, path: str, max_w: int = 380, max_h: int = 280) -> bool:
        """Returns False if the file can't be shown"""
        texture = self._load_texture(path)
        if texture is None:
            return False

        w = ctypes.c_int()
        h = ctypes.c_int()
        sdl2.SDL_QueryTexture(texture, None, None, ctypes.byref(w), ctypes.byref(h))
        tex_w, tex_h = w.value, h.value

        # Anchor on the same center as the description text; clamp max_w
        # symmetrically so the image stays on-screen on both sides.
        desc_center_x = self.screen_width * 3 // 4 - 20
        right_margin = 10
        left_margin = 10
        max_half = min(desc_center_x - left_margin, self.screen_width - right_margin - desc_center_x)
        max_w = min(max_w, 2 * max_half)

        scale = min(max_w / tex_w, max_h / tex_h, 1.0)
        dw, dh = int(tex_w * scale), int(tex_h * scale)

        x = desc_center_x - dw // 2
        y = 40 + (max_h - dh) // 2

        dst_rect = sdl2.SDL_Rect(x, y, dw, dh)
        sdl2.SDL_RenderCopy(self.renderer, texture, None, dst_rect)
        return True

    @functools.lru_cache(maxsize=64)
    def wrap_text(self, text: str, max_width: int) -> Tuple[str, ...]:
        lines = []
        current_line = ""
        for word in text.split():
            while len(word) > 1 and self.get_text_width(word) > max_width:
                fits = len(word) - 1
                while fits > 1 and self.get_text_width(word[:fits]) > max_width:
                    fits -= 1
                lines += [current_line, word[:fits]] if current_line else [word[:fits]]
                current_line, word = "", word[fits:]
            test_line = f"{current_line} {word}".strip()
            if self.get_text_width(test_line) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        return tuple(lines)

    def draw_wrapped_text_centered(
        self,
        text: str,
        center_x: int,
        start_y: int,
        max_width: int,
        line_spacing: int = 2,
        reserve_bottom: int = 0,
    ):

        lines = self.wrap_text(text, max_width)
        line_height = self.font_size + line_spacing
        text_height = len(lines) * line_height

        desc_top_y = start_y
        desc_bottom_y = self.screen_height - self.footer_height - BUTTON_AREA_HEIGHT - reserve_bottom
        max_area_height = desc_bottom_y - desc_top_y

        offset = self._scroll_offset(self._desc_scroll_state, text, text_height - max_area_height)

        for i, line in enumerate(lines):
            line_width = self.get_text_width(line)
            desc_x = center_x - line_width // 2
            desc_y = desc_top_y + i * line_height - offset
            if desc_top_y <= desc_y <= desc_bottom_y - line_height:
                self.draw_text((desc_x, desc_y), line)

    def _load_store_texture(self, name: str):
        filename = STORE_ICON_FILES.get(name)
        return self._load_texture(os.path.join(STORE_ICONS_DIR, filename)) if filename else None

    def draw_port_stores(self, stores, discount_lookup, center_x: int, max_width: int, bottom_y: int):
        """Render the store-icon row for a port.

        discount_lookup: callable(store_name) -> discount percent (0/None if none).
        bottom_y: y of the bottom edge of the reserved area.
        """
        if not stores:
            return

        # Build a list of (texture, discount_text, total_width) per entry.
        gap_after_icon = 4  # px between icon and discount text (if shown)
        gap_between_items = 12  # px between entries
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
        y_text = y_icon + (STORE_ICON_SIZE - self.font_size) // 2

        for tex, disc_text, entry_w in entries:
            dst = sdl2.SDL_Rect(x, y_icon, STORE_ICON_SIZE, STORE_ICON_SIZE)
            sdl2.SDL_RenderCopy(self.renderer, tex, None, dst)
            if disc_text:
                self.draw_text(
                    (x + STORE_ICON_SIZE + gap_after_icon, y_text),
                    disc_text,
                    theme.discount,
                )
            x += entry_w + gap_between_items
