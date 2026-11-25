if (!instance_exists(o_game)) exit;
var _hud = id;
with (o_game)
{
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
        ini_open("configfile");
        ds_off = ini_read_real("section", "no_dualscreen", 0);
        ds_hints = ini_read_real("section", "no_maphints", 0) == 0;
        ini_close();
        ds_wait = 0;
        ds_tick = 0;
        ds_idle = -1;
        ds_room = -1;

        ds_item = -1;
        ds_two = false;
        ds_cursor = 0;

        ds_shot = -1;
        ds_hud = -1;
        ds_page = -1;
        ds_view = -1;
        ds_base = -1;
        ds_map = -1;
        ds_filter = -1;

        ds_sprite = -1;
        ds_seen = [];
        ds_visited = 0;
        ds_scan = 0;
        ds_here = false;
        ds_x = 44;
        ds_y = 10;

        ds_buffer = -1;
        ds_doors = [];
        ds_door_row = 0;

        ds_exits = [];
        ds_goal = [];
        ds_hint_wait = 0;
        ds_paused = false;
        ds_route = [
            ["bosstank", "bosswallrobot", 108, 30],
            ["o_item_railway_key_discovered", "bosswallrobot", 110, 30],
            ["r_mountain_2_railway2o_door_metal", "bosswallrobot", 104, 36],
            ["bosswallrobot", "bossrobot", 92, 39],
            ["bossg92", "bossrobot", 101, 22],
            ["bossrobot", "bosswallace", 130, 18],
            ["o_item_battery_discovered", "bosswallace", 132, 18],
            ["r_office_2_hangar1o_crane_machine", "bosswallace", 124, 24],
            ["bosswallace", "bossgear", 137, 12],
            ["hostage", "bossgear", 126, 11],
            ["o_item_king_sword_discovered", "bossgear", 179, 31],
            ["r_chateau43o_dialog_king_statue", "bossgear", 177, 24],
            ["bossgear", "bosshumanaxel", 178, 24],
            ["klausdialog", "bosshumanaxel", 181, 24],
            ["o_item_valve_handle_discovered", "bosshumanaxel", 120, 34],
            ["r_office_2_foundry6o_foundry_bridge_machine", "bosshumanaxel", 121, 37],
            ["bosshumanaxel", "bossconrad", 121, 34],
            [[85, 34], "bossconrad", 87, 34],
            ["bossconrad", "bosstrashrobo", 51, 24],
            ["o_item_jetmech_key_discovered", "bosstrashrobo", 50, 25],
            ["r_sewers_5o_marker_end_sensor", "bosstrashrobo", 60, 23],
            ["bosstrashrobo", "bossmathias", 154, 34],
            ["o_ability_walljump", "bossmathias", 156, 36],
            ["bossdynamo", "bossmathias", 77, 40],
            ["o_item_icegun", "bossmathias", 79, 40],
            ["r_chateau5o_marker_end_sensor", "bossmathias", 159, 28],
            ["bossmathias", "bosseaston", 154, 28],
            ["o_ability_hawkclaw", "r_jungle_2_bossconrad4o_dialog_plane", 153, 29],
            ["o_item_medallion_left_discovered", "r_jungle_2_bossconrad4o_dialog_plane", 98, 35],
            ["o_ability_groundroll", "r_jungle_2_bossconrad4o_dialog_plane", 69, 36],
            ["o_item_medallion_right_discovered", "r_jungle_2_bossconrad4o_dialog_plane", 63, 35],
            ["r_jungle_2_bossconrad4o_dialog_plane", "bosseaston", 55, 25],
            ["bosseaston", "bosseaston", 54, 32]
        ];

        ds_follow = true;
        ds_zoom = 2;
        ds_pinch = 0;
        ds_cx = 0;
        ds_cy = 0;
        ds_redraw = 0;
    }
    if (!ds_ok) exit;

    if (ds_wait-- <= 0)
    {
        ds_wait = 60;
        var _there = DualScreen_Available() == 1;
        if (DualScreen_Ready() == 1)
        {
            if (!_there || ds_off) DualScreen_Enable(0);
        }
        else if (_there && !ds_off) DualScreen_Enable(1);
    }

    if (paused_) instance_activate_object(obj_text2);
    if (!instance_exists(obj_text2)) instance_create_depth(0, 0, -450, obj_text2);

    if (paused_ && currentmenu == 5)
    {
        var _last = global.endrewards ? 13 : 12;
        ds_two = DualScreen_Available() == 1;
        if (ds_item >= 0)
        {
            if (!ds_two) ds_item = 0;
            var _to = -1;
            if (global.keyPausePressed || global.keyBackPressed || global.keyEscPressed)
            {
                _to = 6;
                if (refreshlang)
                {
                    refresh_all();
                    refreshlang = false;
                }
                if (global.keyPausePressed) alarm[6] = 1;
                else
                {
                    menu5_commited = -1;
                    currentmenu = 0;
                    sfx_play(a_cancel, 7, false);
                }
            }
            else if (global.keyUpPressed) _to = ds_item == 0 ? 6 : _last;
            else if (global.keyDownPressed) _to = ds_item == 0 ? 0 : 7;
            else if ((global.keyLeftPressed || global.keyRightPressed) && ds_two)
            {
                ds_item = 1 - ds_item;
                sfx_play(a_cursor, 7, false);
            }
            else if (global.keyConfirmPressed)
            {
                if (ds_item == 0)
                {
                    ds_hints = !ds_hints;
                    ds_hint_wait = 0;
                    config_save(!ds_hints, "no_maphints");
                }
                else
                {
                    ds_off = !ds_off;
                    ds_wait = 0;
                    config_save(ds_off, "no_dualscreen");
                }
                sfx_play(a_cursor, 7, false);
            }
            if (_to >= 0)
            {
                if (currentmenu == 5) sfx_play(a_cursor, 7, false);
                ds_item = -1;
                menu5_control = true;
                menu5_cursor = _to;
            }
        }
        else if ((global.keyDownPressed && (ds_cursor == 6 || ds_cursor == _last)) || (global.keyUpPressed && (ds_cursor == 0 || ds_cursor == 7)))
        {
            ds_item = ds_cursor >= 7 && ds_two ? 1 : 0;
            menu5_control = false;
            menu5_cursor = -1;
        }
        ds_cursor = menu5_cursor;
    }

    if (ds_door_row < 35 && !paused_)
    {
        if (!buffer_exists(ds_buffer))
        {
            var _picture = surface_create(1128, 280);
            surface_set_target(_picture);
            draw_clear_alpha(c_black, 0);
            draw_sprite_part(s_minimap_blue, 0, 352, 84, 1128, 280, 0, 0);
            surface_reset_target();
            ds_buffer = buffer_create(1263360, buffer_fixed, 1);
            buffer_get_surface(ds_buffer, _picture, 0);
            surface_free(_picture);
        }
        for (var _c = 0; _c < 140; _c++)
        {
            var _at = (ds_door_row * 9024 + _c * 8) * 4;
            var _a = buffer_peek(ds_buffer, _at + 18076, buffer_u32), _b = buffer_peek(ds_buffer, _at + 18080, buffer_u32);
            var _w = buffer_peek(ds_buffer, _at + 27100, buffer_u32);
            if (_a >= 16777216 && _b >= 16777216 && (_a & 12632256) != 12632256 && (_b & 12632256) != 12632256 && (_w & 12632256) == 12632256) array_push(ds_doors, [_c * 8 + 8, ds_door_row * 8 + 4, _c + 44, ds_door_row + 10]);
        }
        ds_door_row++;
        if (ds_door_row == 35) buffer_delete(ds_buffer);
    }

    if (ds_hint_wait-- <= 0 || ds_paused != paused_)
    {
        ds_hint_wait = 60;
        ds_paused = paused_;

        ds_exits = [];
        for (var _n = 0; _n < array_length(ds_doors) && ds_hints; _n++)
        {
            var _door = ds_doors[_n];
            if ((mapGrid[_door[3]][_door[2]] == 1) != (mapGrid[_door[3]][_door[2] + 1] == 1)) array_push(ds_exits, _door);
        }

        ds_goal = [];
        switch (showfortmarker)
        {
            case 1: ds_goal = [96, 23, c_yellow]; break;
            case 2: ds_goal = [146, 25, c_yellow]; break;
            case 3: ds_goal = [141, 30, c_yellow]; break;
            case 4: ds_goal = [143, 35, c_yellow]; break;
            case 105: ds_goal = [159, 28, c_yellow]; break;
            default:
                for (var _n = 0; _n < array_length(ds_route) && ds_hints; _n++)
                {
                    var _step = ds_route[_n];
                    var _done = is_array(_step[0]) ? mapGrid[_step[0][1]][_step[0][0]] == 1 : gs_load(_step[0]);
                    if (_done || gs_load(_step[1])) continue;
                    ds_goal = [_step[2], _step[3], c_orange];
                    break;
                }
                break;
        }
    }

    if (DualScreen_Ready() != 1)
    {
        visible = true;
        obj_text2.visible = true;
        _hud.x = 7;
        if (surface_exists(ds_shot)) surface_free(ds_shot);
        exit;
    }
    ds_idle = -1;

    var _menu = paused_ && currentmenu != 8;
    visible = paused_ && !_menu;
    if (visible) mapx_player = 0;
    obj_text2.visible = false;
    _hud.x = -4000;

    var _color = draw_get_color(), _alpha = draw_get_alpha(), _font = draw_get_font();
    var _ha = draw_get_halign(), _va = draw_get_valign();
    gpu_push_state();
    gpu_set_texfilter(false);
    draw_set_alpha(1);
    draw_set_color(c_white);

    var _camx = camera_get_view_x(view_camera[0]), _camy = camera_get_view_y(view_camera[0]);
    var _camw = camera_get_view_width(view_camera[0]), _camh = camera_get_view_height(view_camera[0]);
    if (_menu)
    {
        if (surface_exists(ds_shot))
        {
            gpu_set_blendenable(false);
            draw_surface_stretched_ext(ds_shot, _camx, _camy, _camw, _camh, c_gray, 1);
            gpu_set_blendenable(true);
        }
    }
    else if (!paused_)
    {
        var _aw = surface_get_width(application_surface), _ah = surface_get_height(application_surface);
        if (surface_exists(ds_shot) && (surface_get_width(ds_shot) != _aw || surface_get_height(ds_shot) != _ah)) surface_free(ds_shot);
        var _fresh = !surface_exists(ds_shot);
        if (_fresh) ds_shot = surface_create(_aw, _ah);
        if (_fresh || ds_tick mod 2 == 0) surface_copy(ds_shot, 0, 0, application_surface);

        if (surface_exists(ds_hud))
        {
            gpu_set_blendmode_ext(bm_one, bm_inv_src_alpha);
            draw_surface_part_ext(ds_hud, 0, 57, 170, 48, _camx, _camy + 7 * _camh / 360, _camw / 640, _camh / 360, c_white, 1);
            gpu_set_blendmode(bm_normal);
        }
    }

    var _scale = max(1, floor(DualScreen_Width() / 620));
    var _vw = ceil(DualScreen_Width() / _scale), _vh = ceil(DualScreen_Height() / _scale);
    var _ix = 11, _iy = 83, _iw = _vw - 22, _ih = _vh - 127;
    var _pw = min(640, _vw), _px = (640 - _pw) div 2;

    var _text = DualScreen_Touch();
    if (_text != "")
    {
        var _touch = json_parse(_text);
        var _tx = _touch.x / _scale, _ty = _touch.y / _scale;
        if (_menu)
        {
            if (_touch.tap && currentmenu == 0 && menu_control && !quit_note)
            {
                var _item = floor((_ty - 78 + 17 - 72) / 26);
                _tx += _px - (_vw - _pw) div 2;
                if (_tx >= 484 && _tx < 600 && _item >= 0 && _item < menu_items)
                {
                    menu_cursor = _item;
                    menu_commited = _item;
                    menu_control = false;
                    sfx_play(a_confirm, 7, false);
                }
            }
        }
        else if (point_in_rectangle(_touch.originX / _scale, _touch.originY / _scale, _ix, _iy, _ix + _iw, _iy + _ih))
        {
            if (_touch.tap) ds_follow = true;
            if (_touch.dx != 0 || _touch.dy != 0)
            {
                ds_follow = false;
                ds_cx -= _touch.dx / _scale / ds_zoom;
                ds_cy -= _touch.dy / _scale / ds_zoom;
            }
            ds_pinch += _touch.zoom;
            if (abs(ds_pinch) > 0.4)
            {
                ds_zoom = clamp(ds_zoom + sign(ds_pinch), 1, 4);
                ds_pinch = 0;
            }
            ds_redraw = 0;
        }
    }

    ds_tick++;
    if (_menu || _text != "" || ds_tick mod 2 == 0)
    {
        if (!surface_exists(ds_hud)) ds_hud = surface_create(640, 360);
        surface_set_target(ds_hud);
        draw_clear_alpha(c_black, 0);
        gpu_set_blendmode_ext_sepalpha(bm_src_alpha, bm_inv_src_alpha, bm_one, bm_inv_src_alpha);
        with (_hud)
        {
            if (other.paused_)
            {
                phealth = other.phealth;
                pmaxhealth = other.pmaxhealth;
                pmagic = other.pmagic;
                pmaxmagic = other.pmaxmagic;
                pbop = other.pbop;
                pmaxbop = other.pmaxbop;
            }
            var _health = draw_health_, _magic = draw_magic_, _boss = draw_bb_, _mech = draw_mb_, _boss_alpha = bossalpha, _mech_alpha = mechalpha;
            x = 7;
            event_perform(ev_draw, ev_gui);
            x = -4000;
            draw_health_ = _health;
            draw_magic_ = _magic;
            draw_bb_ = _boss;
            draw_mb_ = _mech;
            bossalpha = _boss_alpha;
            mechalpha = _mech_alpha;
        }
        gpu_set_blendmode(bm_normal);
        surface_reset_target();

        if (_menu)
        {
            if (!surface_exists(ds_page)) ds_page = surface_create(640, 360);
            surface_set_target(ds_page);
            draw_clear(c_black);
            event_perform(ev_draw, ev_gui);
            with (obj_text2) event_perform(ev_draw, ev_gui);
            surface_reset_target();
            draw_set_alpha(1);
        }

        if (!paused_)
        {
            ds_here = activate_map_tracking && mapx_player != 0 && !global.iswarping;
            if (ds_here)
            {
                var _cx = global.map_x + (local_x div 640), _cy = global.map_y + (local_y div 360);
                if (ds_x != _cx || ds_y != _cy) ds_redraw = 0;
                ds_x = _cx;
                ds_y = _cy;
                if (ds_room != room)
                {
                    ds_room = room;
                    event_user(12);
                    ds_redraw = 0;
                }

                var _sprite = global.scanlines == 3 ? s_minimap_simple : s_minimap_blue;
                if (!surface_exists(ds_map) || ds_sprite != _sprite)
                {
                    if (!surface_exists(ds_map)) ds_map = surface_create(1128, 280);
                    surface_set_target(ds_map);
                    draw_clear_alpha(c_black, 0);
                    surface_reset_target();
                    ds_sprite = _sprite;
                    ds_seen = array_create(4935, 0);
                    ds_visited = 0;
                }
                ds_scan = (ds_scan + 1) mod 35;
                surface_set_target(ds_map);
                for (var _n = 0; _n <= 141; _n++)
                {
                    var _c = _n < 141 ? _n : ds_x - 44, _r = _n < 141 ? ds_scan : ds_y - 10;
                    if (_c < 0 || _c > 140 || _r < 0 || _r > 34) continue;
                    var _state = mapGrid[_r + 10][_c + 44], _old = ds_seen[_r * 141 + _c];
                    if (_old == _state) continue;
                    ds_seen[_r * 141 + _c] = _state;
                    if (_state == 1) ds_visited++;
                    if (_old == 1) ds_visited--;
                    ds_redraw = 0;
                    gpu_set_blendmode_ext(bm_zero, bm_zero);
                    draw_sprite_ext(s_map_black_dot, 0, _c * 8, _r * 8, 8, 8, 0, c_white, 1);
                    gpu_set_blendmode(bm_normal);
                    if (_state != 0) draw_sprite_part_ext(_sprite, 0, (_c + 44) * 8, (_r + 10) * 8 + 4, 8, 8, _c * 8, _r * 8, 1, 1, _state == 1 ? c_white : c_gray, 1);
                }
                surface_reset_target();
            }
        }

        var _mw = _iw / ds_zoom, _mh = _ih / ds_zoom;
        if (ds_follow)
        {
            ds_cx = (ds_x - 44) * 8 + 4;
            ds_cy = (ds_y - 10) * 8 + 4;
        }
        ds_cx = _mw >= 1128 ? 564 : clamp(ds_cx, _mw / 2, 1128 - _mw / 2);
        ds_cy = _mh >= 280 ? 140 : clamp(ds_cy, _mh / 2, 280 - _mh / 2);
        var _sx = floor(ds_cx - _mw / 2), _sy = floor(ds_cy - _mh / 2);

        if (!surface_exists(ds_base) || surface_get_width(ds_base) != _iw || surface_get_height(ds_base) != _ih)
        {
            if (surface_exists(ds_base)) surface_free(ds_base);
            ds_base = surface_create(_iw, _ih);
            ds_redraw = 0;
        }
        if (ds_redraw-- <= 0)
        {
            ds_redraw = 30;
            surface_set_target(ds_base);
            draw_clear(c_black);
            var _cell = 8 * ds_zoom;
            for (var _g = (_cell - (_sx * ds_zoom) mod _cell) mod _cell; _g < _iw; _g += _cell) draw_sprite_ext(s_map_white_dot, 0, _g, 0, 1, _ih, 0, c_white, 0.06);
            for (var _g = (_cell - (_sy * ds_zoom) mod _cell) mod _cell; _g < _ih; _g += _cell) draw_sprite_ext(s_map_white_dot, 0, 0, _g, _iw, 1, 0, c_white, 0.06);
            if (surface_exists(ds_map)) draw_surface_ext(ds_map, -_sx * ds_zoom, -_sy * ds_zoom, ds_zoom, ds_zoom, 0, c_white, 1);
            var _places = [[showrailwaymarker, 104.5, 36, 14213739], [showbatterymarker, 124, 24, 3191852], [showkingmarker, 177, 24, 60927], [showvalvemarker, 121, 37, 677847], [showairplanemarker, 55, 25, 33791]];
            for (var _n = 0; _n < 5; _n++)
            {
                if (_places[_n][0]) draw_sprite_ext(s_legend_icon_white, 0, ((_places[_n][1] - 44) * 8 + 4 - _sx) * ds_zoom, ((_places[_n][2] - 10) * 8 + 4 - _sy) * ds_zoom, ds_zoom / 2, ds_zoom / 2, 0, _places[_n][3], 1);
            }
            for (var _n = 0; _n < markercount; _n++)
            {
                draw_sprite_ext(s_map_pin, 0, ((marker_x[_n] - 44) * 8 - _sx) * ds_zoom, ((marker_y[_n] - 10) * 8 - _sy) * ds_zoom, ds_zoom, ds_zoom, 0, getpinblend(marker_color[_n]), marker_alpha[_n]);
            }
            surface_reset_target();
        }

        if (surface_exists(ds_view) && (surface_get_width(ds_view) != _vw || surface_get_height(ds_view) != _vh)) surface_free(ds_view);
        if (!surface_exists(ds_view)) ds_view = surface_create(_vw, _vh);
        surface_set_target(ds_view);
        draw_clear(c_black);

        var _top = _iy, _from = 0, _rows = _ih;
        if (_menu)
        {
            _top = 419;
            _rows = currentmenu == 10 ? 0 : _vh - 430;
            if (_rows < 40) _rows = 0;
            _from = floor(clamp((ds_cy - _sy) * ds_zoom - _rows / 2, 0, max(0, _ih - _rows)));
        }

        if (global.windowcolor) scrSetWindowColor();
        draw_sprite_stretched(s_options_box_topbottom, 0, 6, 6, _vw - 12, 66);
        if (_menu && currentmenu == 10) draw_sprite_stretched(s_options_box_settings_list, 0, 6, 78, _vw - 12, _vh - 84);
        if (_rows > 0)
        {
            draw_sprite_stretched(s_options_box_settings_list, 0, 6, _top - 5, _vw - 12, _rows + 10);
            draw_sprite_stretched(s_options_box_settings_list, 0, _ix - 1, _top - 1, _iw + 2, _rows + 2);
        }
        if (!_menu) draw_sprite_stretched(s_options_box_topbottom, 0, 6, _vh - 33, _vw - 12, 27);
        shader_reset();

        gpu_set_blendmode_ext(bm_one, bm_inv_src_alpha);
        draw_surface_part_ext(ds_hud, 7, 7, 131, 21, 20, 18, 2, 2, c_white, 1);
        draw_surface_part_ext(ds_hud, 0, 29, 152, 27, _vw - 318, 12, 2, 2, c_white, 1);
        gpu_set_blendmode(bm_normal);

        if (_menu)
        {
            gpu_set_blendenable(false);
            if (currentmenu == 10) draw_surface_part(ds_page, 17, 0, 606, 360, (_vw - 606) div 2, 79 + (_vh - 446) div 2);
            else draw_surface_part(ds_page, _px, 17, _pw, 330, (_vw - _pw) div 2, 78);
            gpu_set_blendenable(true);
        }

        if (_rows > 0)
        {
            draw_surface_part(ds_base, 0, _from, _iw, _rows, _ix, _top);
            var _ox = _ix - _sx * ds_zoom, _oy = _top - _from - _sy * ds_zoom;
            var _x1 = _ix + 8, _y1 = _top + 8, _x2 = _ix + _iw - 8, _y2 = _top + _rows - 8;

            var _pulse = 0.65 + 0.35 * sin(current_time / 250);
            for (var _n = 0; _n < array_length(ds_exits) && ds_hints; _n++)
            {
                var _ex = _ox + ds_exits[_n][0] * ds_zoom, _ey = _oy + ds_exits[_n][1] * ds_zoom;
                if (!point_in_rectangle(_ex, _ey, _x1, _y1, _x2, _y2)) continue;
                draw_sprite_ext(s_map_white_dot, 0, _ex, _ey - 6, 8.5, 8.5, -45, c_black, 1);
                draw_sprite_ext(s_map_white_dot, 0, _ex, _ey - 4, 5.7, 5.7, -45, #FFE65A, _pulse);
            }

            if (array_length(ds_goal) > 0)
            {
                var _gx = _ox + ((ds_goal[0] - 44) * 8 + 4) * ds_zoom, _gy = _oy + ((ds_goal[1] - 10) * 8 + 4) * ds_zoom;
                if (point_in_rectangle(_gx, _gy, _x1, _y1, _x2, _y2)) draw_sprite_ext(s_map_warp_position, fx2_image_index, _gx, _gy, ds_zoom / 2, ds_zoom / 2, 0, ds_goal[2], 1);
                else
                {
                    var _ax = clamp(_gx, _x1 + 6, _x2 - 6), _ay = clamp(_gy, _y1 + 6, _y2 - 6);
                    draw_sprite_ext(s_dialog_select_arrow, 0, _ax, _ay, 2, 2, point_direction(_ax, _ay, _gx, _gy), ds_goal[2], _pulse);
                }
            }

            var _mx = _ox + ((ds_x - 44) * 8 + 4) * ds_zoom, _my = _oy + ((ds_y - 10) * 8 + 4) * ds_zoom;
            if (ds_here && point_in_rectangle(_mx, _my, _x1, _y1, _x2, _y2)) draw_sprite_ext(s_map_player_position, fx_image_index, _mx, _my, 2, 2, 0, c_white, 1);
        }

        if (!_menu)
        {
            if (_hud.showbossbar)
            {
                gpu_set_blendmode_ext(bm_one, bm_inv_src_alpha);
                draw_surface_part_ext(ds_hud, 368, 2, 272, 24, _ix + (_iw - 544) div 2, _iy + 4, 2, 2, c_white, 1);
                gpu_set_blendmode(bm_normal);
            }
            draw_set_color(c_white);
            draw_set_font(global.dfont2);
            draw_set_valign(fa_middle);
            draw_set_halign(fa_left);
            draw_text(20, _vh - 19, str_Map + ": " + string_format(ds_visited / 1369 * 100, 0, 1) + "%");
            draw_set_halign(fa_right);
            draw_text(_vw - 20, _vh - 19, string(global.goldnum));
            draw_sprite(s_gold_indicator, 0, _vw - 40 - string_width(string(global.goldnum)), _vh - 26);
        }

        if (global.scanlines == 3 && instance_exists(crt))
        {
            surface_reset_target();
            if (surface_exists(ds_filter) && (surface_get_width(ds_filter) != _vw || surface_get_height(ds_filter) != _vh)) surface_free(ds_filter);
            if (!surface_exists(ds_filter)) ds_filter = surface_create(_vw, _vh);
            surface_set_target(ds_filter);
            matrix_set(matrix_world, matrix_build(0, 0, 0, 0, 0, 0, _vw / 640, _vh / 360, 1));
            var _grid = global.gbgridoff, _view = ds_view;
            global.gbgridoff = 1;
            surface_set_target(ds_hud);
            with (crt)
            {
                var _surf = surf;
                surf = _view;
                event_perform(ev_draw, ev_gui_end);
                surf = _surf;
            }
            global.gbgridoff = _grid;
            matrix_set(matrix_world, matrix_build_identity());
        }

        var _sent = DualScreen_Begin() == 1;
        if (_sent) DualScreen_Draw(0, 0, _vw * _scale, _vh * _scale, 0, 0, 1, 1, 1, 0);
        surface_reset_target();
        if (_sent) DualScreen_End();
    }

    gpu_pop_state();
    draw_set_color(_color);
    draw_set_alpha(_alpha);
    draw_set_font(_font);
    draw_set_halign(_ha);
    draw_set_valign(_va);
}
