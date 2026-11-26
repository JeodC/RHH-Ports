if (!variable_instance_exists(id, "ds_ok"))
{
    ds_ok = false;
    try
    {
        ds_ok = DualScreen_Available() >= 0;
    }
    catch (_error)
    {
    }
    ds_wait = 0;
    ds_tick = 0;
    ds_menu = false;
    ds_hidden = false;
    ds_idle = false;
    ds_hud = -1;
    ds_page = -1;
    ds_map = -1;
    ds_view = -1;
}
if (!ds_ok) exit;

if (ds_wait-- <= 0)
{
    ds_wait = 60;
    var _there = DualScreen_Available() == 1;
    if (DualScreen_Ready() == 1)
    {
        if (!_there) DualScreen_Enable(0);
    }
    else if (_there)
    {
        DualScreen_Enable(1);
        ds_idle = false;
    }
}

var _ready = DualScreen_Ready() == 1;
ds_menu = _ready && instance_exists(par_menu) && !instance_exists(menu_title) && !instance_exists(submenu_file_select);
var _menu = ds_menu;
with (obj_HUD) visible = !_ready;
with (obj_map_system) visible = !_ready;
if (_menu || ds_hidden)
{
    with (par_menu) visible = !_menu;
    ds_hidden = _menu;
}
if (!_ready) exit;

if (_menu && sprite_exists(global.spr_screen))
{
    var _cam = view_camera[0];
    draw_sprite_ext(global.spr_screen, 0, camera_get_view_x(_cam), camera_get_view_y(_cam), camera_get_view_width(_cam) / sprite_get_width(global.spr_screen), camera_get_view_height(_cam) / sprite_get_height(global.spr_screen), 0, c_white, 1);
}

var _scale = max(1, floor(DualScreen_Width() / 310));
var _vw = ceil(DualScreen_Width() / _scale), _vh = ceil(DualScreen_Height() / _scale);
var _x = (_vw - 320) div 2, _y = (_vh - 240) div 2;
var _band = global.HUD_size + 6;

var _text = DualScreen_Touch();
if (_text != "" && _menu)
{
    var _touch = json_parse(_text);
    var _tx = _touch.x / _scale - _x - 160, _ty = _touch.y / _scale - _y - 120;
    with (menu_choice)
    {
        if (_touch.tap && selection == 0 && !instance_exists(par_submenu) && abs(offset_y) <= 2 && alarm[0] < 1 && point_distance(0, 0, _tx, _ty) > 24)
        {
            selection = abs(_tx) > abs(_ty) ? (_tx < 0 ? 3 : 4) : (_ty < 0 ? 1 : 2);
            bitsound(sndMessageConfirm);
            alarm[0] = 30;
        }
    }
}

var _idle = !_menu && !instance_exists(par_player);
if (_idle && ds_idle) exit;
ds_idle = _idle;
ds_tick++;
if (!_menu && !_idle && (ds_tick mod 2 == 1 || global.cutscene)) exit;

var _color = draw_get_color(), _alpha = draw_get_alpha(), _font = draw_get_font();
var _ha = draw_get_halign(), _va = draw_get_valign();
gpu_push_state();
gpu_set_texfilter(false);
draw_set_alpha(1);
draw_set_color(c_white);

if (_menu)
{
    if (!surface_exists(ds_page)) ds_page = surface_create(320, 240);
    surface_set_target(ds_page);
    draw_clear(c_black);
    with (par_menu) event_perform(ev_draw, ev_gui);
    with (obj_map_system)
    {
        if (map_on || shrinking) event_perform(ev_draw, ev_gui_end);
    }
    with (par_menu) event_perform(ev_draw, ev_gui_end);
    with (menu_choice)
    {
        if (selection == 0 && !instance_exists(par_submenu))
        {
            var _cy = 120 + round(offset_y);
            draw_set_color(c_white);
            draw_triangle(160, _cy - 92, 155, _cy - 84, 165, _cy - 84, false);
            draw_triangle(160, _cy + 92, 155, _cy + 84, 165, _cy + 84, false);
            draw_triangle(68, _cy, 76, _cy - 5, 76, _cy + 5, false);
            draw_triangle(252, _cy, 244, _cy - 5, 244, _cy + 5, false);
            draw_text_scribble(160, _cy - 102, "[fnt_Logbook][c_white][fa_center][fa_middle]Map");
            draw_text_scribble(160, _cy + 102, "[fnt_Logbook][c_white][fa_center][fa_middle]Options");
            draw_text_scribble(62, _cy, "[fnt_Logbook][c_white][fa_right][fa_middle]Logbook");
            draw_text_scribble(258, _cy, "[fnt_Logbook][c_white][fa_left][fa_middle]Inventory");
        }
    }
    surface_reset_target();
}
else if (!_idle)
{
    if (!surface_exists(ds_hud)) ds_hud = surface_create(320, global.HUD_size + 4);
    surface_set_target(ds_hud);
    draw_clear_alpha(c_black, 0);
    with (obj_HUD) event_perform(ev_draw, ev_gui);
    surface_reset_target();

    var _mh = _vh - _band;
    if (surface_exists(ds_map) && (surface_get_width(ds_map) != _vw || surface_get_height(ds_map) != _mh)) surface_free(ds_map);
    if (!surface_exists(ds_map)) ds_map = surface_create(_vw, _mh);
    surface_set_target(ds_map);
    draw_clear(c_black);
    with (obj_map_system)
    {
        if (!variable_instance_exists(id, "draw_map")) event_perform(ev_draw, ev_gui_end);
        draw_clear(c_black);
        if (map_area == global.area)
        {
            map_scale = 1;
            draw_map(map_x * 8 + 4 - _vw / 2, map_y * 8 + 4 - _mh / 2, 0);
            draw_text_scribble(6, 6, "[fnt_Big][c_white][fa_left][fa_top]" + col_txt + get_area_name(map_area));
        }
    }
    surface_reset_target();
}

if (surface_exists(ds_view) && (surface_get_width(ds_view) != _vw || surface_get_height(ds_view) != _vh)) surface_free(ds_view);
if (!surface_exists(ds_view)) ds_view = surface_create(_vw, _vh);
surface_set_target(ds_view);
draw_clear(c_black);
if (_menu) draw_surface(ds_page, _x, _y);
else if (!_idle)
{
    draw_surface(ds_map, 0, _band);
    draw_surface(ds_hud, _x, 4);
}
var _sent = DualScreen_Begin() == 1;
if (_sent) DualScreen_Draw(0, 0, _vw * _scale, _vh * _scale, 0, 0, 1, 1, 1, 0);
surface_reset_target();
gpu_pop_state();
if (_sent) DualScreen_End();
draw_set_color(_color);
draw_set_alpha(_alpha);
draw_set_font(_font);
draw_set_halign(_ha);
draw_set_valign(_va);
