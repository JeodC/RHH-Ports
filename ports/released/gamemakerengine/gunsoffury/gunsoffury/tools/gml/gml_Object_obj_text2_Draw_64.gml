if (!instance_exists(o_game)) exit;
with (o_game)
{
    if (!paused_ || !variable_instance_exists(id, "ds_ok")) exit;
    draw_set_alpha(1);
    if (currentmenu == 5)
    {
        draw_set_font(global.dfont2);
        draw_set_halign(fa_left);
        draw_set_valign(fa_middle);
        if (global.windowcolor) scrSetWindowColor();
        draw_sprite_ext(s_options_box_topbottom, 0, xx + 37, yy + 278, 141, 1, 0, c_white, 1);
        if (ds_item >= 0) draw_sprite_ext(s_options_box_items_list_highlight, 0, xx + 37 + 282 * ds_item, yy + 278, 94, 1, 0, make_colour_rgb(glownum, glownum, glownum), 1);
        shader_reset();
        draw_set_color(c_white);
        draw_text(xx + 51, yy + 292, "Map Hints");
        if (ds_two) draw_text(xx + 333, yy + 292, "Second Screen");
        draw_set_color(c_yellow);
        draw_text(xx + 211 + langx, yy + 292, ds_hints ? str_On : str_Off);
        if (ds_two) draw_text(xx + 493 + langx, yy + 292, ds_off ? str_Off : str_On);
        draw_set_color(c_white);
    }
    else if (currentmenu == 10 && ds_hints && !showlegend && !teleportmap)
    {
        var _pulse = 0.65 + 0.35 * sin(current_time / 250);
        var _ox = (mapix + mapx_offset) * mapzoom, _oy = (mapiy + mapy_offset) * mapzoom;
        var _d = 1 + 1.5 * mapzoom;
        for (var _n = 0; _n < array_length(ds_exits); _n++)
        {
            var _ex = _ox + (ds_exits[_n][0] + 352) * mapzoom, _ey = _oy + (ds_exits[_n][1] + 84) * mapzoom;
            draw_sprite_ext(s_map_white_dot, 0, _ex, _ey - _d - 1, (_d + 1) * 1.42, (_d + 1) * 1.42, -45, c_black, 1);
            draw_sprite_ext(s_map_white_dot, 0, _ex, _ey - _d, _d * 1.42, _d * 1.42, -45, #FFE65A, _pulse);
        }
        if (array_length(ds_goal) > 0 && showfortmarker == 0)
        {
            var _gx = _ox + (ds_goal[0] * 8 + 4) * mapzoom, _gy = _oy + (ds_goal[1] * 8 + 8) * mapzoom;
            if (point_in_rectangle(_gx, _gy, 10, 10, 630, 350)) draw_sprite_ext(s_map_warp_position, fx2_image_index, _gx, _gy, max(0.4, mapzoom / 2), max(0.4, mapzoom / 2), 0, ds_goal[2], 1);
            else
            {
                var _ax = clamp(_gx, 20, 620), _ay = clamp(_gy, 40, 340);
                draw_sprite_ext(s_dialog_select_arrow, 0, _ax, _ay, 2, 2, point_direction(_ax, _ay, _gx, _gy), ds_goal[2], _pulse);
            }
        }
    }
}
