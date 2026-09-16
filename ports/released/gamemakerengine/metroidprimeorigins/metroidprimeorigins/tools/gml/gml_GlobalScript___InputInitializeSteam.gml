function __InputInitializeSteam()
{
    with (__InputSystem())
    {
        __usingSteam = false;
        __usingSteamworks = false;
        __usingBigPicture = false;
        __onSteamDeck = false;
        __onWINE = false;
        __steamHandlesArray = [];
        __steamSwitchLabels = false;
        __steamTypeToInputTypeMap = ds_map_create();
        __steamTypeToDescriptionMap = ds_map_create();
        __steamInputTypeIgnoreMap = ds_map_create();
    }
}
