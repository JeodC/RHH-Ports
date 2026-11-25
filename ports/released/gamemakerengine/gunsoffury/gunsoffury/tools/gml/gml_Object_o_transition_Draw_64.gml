if (!instance_exists(o_healthbar))
{
    with (o_game)
    {
        if (variable_instance_exists(id, "ds_ok") && ds_ok && DualScreen_Ready() == 1 && (ds_idle != room || ds_wait-- <= 0))
        {
            ds_idle = room;
            ds_wait = 60;
            if (DualScreen_Available() != 1) DualScreen_Enable(0);
            else
            {
                var _scale = max(1, floor(DualScreen_Width() / 620));
                var _vw = ceil(DualScreen_Width() / _scale), _vh = ceil(DualScreen_Height() / _scale);
                if (surface_exists(ds_view) && (surface_get_width(ds_view) != _vw || surface_get_height(ds_view) != _vh)) surface_free(ds_view);
                if (!surface_exists(ds_view)) ds_view = surface_create(_vw, _vh);
                surface_set_target(ds_view);
                draw_clear(c_black);
                if (room == r_title_screen || room == r_select_file) draw_sprite_ext(s_logo_fury, 0, _vw / 2, _vh / 2, 2, 2, 0, c_white, 1);
                var _sent = DualScreen_Begin() == 1;
                if (_sent) DualScreen_Draw(0, 0, _vw * _scale, _vh * _scale, 0, 0, 1, 1, 1, 0);
                surface_reset_target();
                if (_sent) DualScreen_End();
            }
        }
    }
}

if (mode != 0)
{
    draw_set_color(c_black);
    draw_set_alpha(percent / 100);
    draw_rectangle(0, 0, wid_, hei_, false);
    draw_set_alpha(1);
}
