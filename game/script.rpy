# This is only the demo. Copy game/lintools/ to reuse the library.
define e = Character("LinTools", color="#75dccb", what_size=40, what_line_spacing=16)

define lintools_demo_cards = (
    ("01 / 彩虹", "{ltrainbow}今天也要闪闪发光。{/ltrainbow}"),
    ("02 / 组合", "{ltfx=wave:amplitude=7;speed=1|rainbow:speed=0.3}波浪与彩虹，一起流动。{/ltfx}"),
    ("03 / 躲开鼠标", "{ltrepel=radius=110;distance=18}{size=42}别靠这么近，我会躲开的。{/size}{/ltrepel}"),
    ("04 / 交互水波", "{ltwater=strength=0.8;speed=260;damping=1.2;distance=48}{size=42}{color=#a7e4ee}静水无声，指尖掠过，涟漪向两岸散去。{/color}{/size}{/ltwater}"),
    ("05 / 破碎", "{ltshatter=hold=0;pieces=4;distance=28;gravity=180;duration=1.2;auto=0}{size=42}短暂一颤，文字随即崩开四散下坠。{/size}{/ltshatter}"),
)

screen lintools_demo_gallery():
    default shatter_preview = lintools_text.ReplayableShatterText(lintools_demo_cards[-1][1], size=42, color="#ffffff")
    modal True
    add Solid("#101823")
    frame:
        background None
        xfill True
        yfill True
        padding (90, 52)
        vbox:
            spacing 20
            text "LinTools / 文字特效" size 54 color "#eff7ff"
            viewport:
                ysize 730
                mousewheel True
                draggable True
                scrollbars "vertical"
                vbox:
                    spacing 16
                    xfill True
                    for title, sample in lintools_demo_cards:
                        frame:
                            background Solid("#1b2939")
                            xfill True
                            padding (28, 18)
                            vbox:
                                spacing 12
                                fixed:
                                    ysize 42
                                    text title size 29 color "#75dccb" yalign 0.5
                                    if title == "05 / 破碎":
                                        textbutton "重播":
                                            xalign 1.0
                                            yalign 0.5
                                            text_size 25
                                            action Function(shatter_preview.replay)
                                if title == "05 / 破碎":
                                    fixed:
                                        ysize 200
                                        add shatter_preview
                                elif title == "04 / 交互水波":
                                    text "上下划过文字，轻触微漾，快速穿过激起波浪。" size 22 color "#8ea7ae"
                                    fixed:
                                        ysize 200
                                        text sample size 42 color "#ffffff" slow_cps 0 yalign 0.5
                                else:
                                    text sample size 42 color "#ffffff" slow_cps 0 yminimum 76:
                                        outlines [(1, "#080e16", 0, 0)]
                                text sample.replace("{", "{{") substitute False size 20 color "#b5c9dc"
            hbox:
                spacing 36
                textbutton "逐句演示 →" action Return("dialogue") text_size 29
                textbutton "破碎 / 鼠标演示" action Return("interactive") text_size 29
                textbutton "帘幕 →" action Return("curtain") text_size 29
                textbutton "返回主菜单" action MainMenu(confirm=False) text_size 29

label start:
    scene expression Solid("#101823")
    window hide
    call screen lintools_demo_gallery
    if _return == "curtain":
        jump lintools_demo_curtain
    if _return == "interactive":
        jump lintools_demo_interactive
    jump lintools_demo_dialogue

define lintools_demo_curtain_source = "　　风拂过这一帘文字　　\n　山色入帘青意满窗　　\n春光落在每一根细绳上　\n　轻轻拨动便泛起涟漪　\n字与字相连随风摇曳　　\n　时光从指尖缓缓流过　\n人间有味是清欢　　　\n　　等风停也等你归来　"

screen lintools_demo_curtain_window():
    default curtain = lintools_text.CurtainText(
        lintools_demo_curtain_source, subdivisions=8)
    modal True
    add Solid("#101823")
    frame:
        background None
        xfill True
        yfill True
        padding (70, 36)
        vbox:
            spacing 18
            fixed:
                ysize 64
                text "LinTools / 帘幕" size 52 color "#eff7ff" yalign 0.5
                hbox:
                    xalign 1.0
                    yalign 0.5
                    spacing 36
                    textbutton "复位" action Function(curtain.reset) text_size 28
                    textbutton "返回总览" action Return() text_size 28
            frame:
                background Solid("#172630")
                xfill True
                ysize 700
                add curtain xalign 0.5 yalign 0.5
            text lintools_demo_curtain_source size 18 color "#8ea7ae" substitute False
    key "game_menu" action Return()

label lintools_demo_curtain:
    window hide
    call screen lintools_demo_curtain_window
    jump start

label lintools_demo_dialogue:
    scene expression Solid("#101823")
    window auto
    e "{ltrainbow=speed=0.25;spread=0.08}红橙黄绿青蓝紫，颜色顺着文字流动。{/ltrainbow}"
    e "{ltfx=wave:amplitude=7;speed=1|rainbow:speed=0.35}既有起伏，也有流动的彩虹。{/ltfx}"
    jump lintools_demo_interactive

label lintools_demo_interactive:
    scene expression Solid("#101823")
    window auto
    e "{ltshatter=hold=0;stagger=0.2;duration=1.2;pieces=4;distance=28;gravity=180}{size=40}那些未曾说出口的话，终于碎在了风里。{/size}{/ltshatter}"
    e "风停了。"
    e "{ltrepel=radius=110;distance=18;response=12}{size=40}别靠这么近，我会躲开的。{/size}{/ltrepel}"
    e "{ltwater}{size=40}{color=#a7e4ee}上下划过这片文字，波纹会从指尖向两边散开。{/color}{/size}{/ltwater}"
    menu:
        "演示结束，接下来……"
        "回到特效总览":
            jump start
        "再看一次逐句演示":
            jump lintools_demo_dialogue
        "重播破碎与鼠标演示":
            jump lintools_demo_interactive
        "返回主菜单":
            return
