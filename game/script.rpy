# This is only the demo. Copy game/lintools/ to reuse the library.
define e = Character("LinTools", color="#75dccb", what_size=40, what_line_spacing=16)

define lintools_demo_rope_source = "两端固定，拖动中间的字拉起弹力绳。"
define lintools_demo_curtain_source = "　　风拂过这一帘文字　　\n　山色入帘青意满窗　　\n春光落在每一根细绳上　\n　轻轻拨动便泛起涟漪　\n字与字相连随风摇曳　　\n　时光从指尖缓缓流过　\n人间有味是清欢　　　\n　　等风停也等你归来　"

define lintools_demo_cards = (
    ("01 / 彩虹", "{ltrainbow}今天也要闪闪发光。{/ltrainbow}"),
    ("02 / 组合", "{ltfx=wave:amplitude=7;speed=1|rainbow:speed=0.3}波浪与彩虹，一起流动。{/ltfx}"),
    ("03 / 躲开鼠标", "{ltrepel=radius=110;distance=18}{size=48}别靠这么近，我会躲开的。{/size}{/ltrepel}"),
    ("04 / 交互水波", "{ltwater=strength=0.8;speed=260;damping=1.2;distance=48}{size=48}{color=#a7e4ee}静水无声，指尖掠过，涟漪向两岸散去。{/color}{/size}{/ltwater}"),
    ("05 / 破碎", "{ltshatter=hold=0;pieces=4;distance=28;gravity=180;duration=1.2;auto=0}{size=48}短暂一颤，文字随即崩开四散下坠。{/size}{/ltshatter}"),
    ("06 / 弹力绳", "{ltrope=size=48;stiffness=18;coupling=380;damping=2.8}" + lintools_demo_rope_source + "{/ltrope}"),
    ("07 / 帘幕", "{ltcurtain=cell=64;size=48;subdivisions=8}" + lintools_demo_curtain_source + "{/ltcurtain}"),
)

init 2 python:
    class LinToolsRopeSlot(renpy.Displayable):
        """Reserve the rope's natural size inside the scrolling card."""
        def __init__(self, rope):
            super(LinToolsRopeSlot, self).__init__()
            self.rope = rope

        def visit(self):
            return [self.rope]

        def render(self, width, height, st, at):
            child = renpy.render(self.rope, width, height, st, at)
            return renpy.Render(*child.get_size())

    class LinToolsGalleryRope(renpy.Displayable):
        """Draw above the gallery, following the slot's actual layout offsets.

        This demo uses ordinary untransformed containers. Walking their placed
        offsets keeps the foreground aligned without hardcoding card heights.
        """
        def __init__(self, source):
            super(LinToolsGalleryRope, self).__init__()
            self.rope = lintools_text.ElasticRopeText(source, size=48)
            self.slot = LinToolsRopeSlot(self.rope)
            self.control_hovered = False

        def visit(self):
            return [self.rope]

        def release(self):
            self.rope.release()

        def hover_control(self, hovered):
            self.control_hovered = hovered
            # Update the live viewport without rebuilding the gallery on hover.
            # Repeated layout can shift text at fractional window scales.
            viewport = renpy.get_displayable("lintools_demo_gallery", "gallery_viewport")
            if viewport is not None:
                viewport.draggable = not hovered
                if hovered:
                    viewport.drag_position = None
            if hovered:
                self.release()

        def reset(self):
            self.rope.reset()
            renpy.redraw(self, 0)

        def scrolled(self, value):
            self.release()
            renpy.redraw(self, 0)

        def per_interact(self):
            renpy.redraw(self, 0)

        def locate(self):
            from renpy.display.viewport import Viewport
            screen = renpy.get_screen("lintools_demo_gallery")
            if screen is None or screen.child is None:
                return None

            def walk(node, x, y, clip):
                if node is self.slot:
                    return x, y, clip
                if isinstance(node, Viewport):
                    clip = (max(clip[0], x), max(clip[1], y),
                        min(clip[2], x+node.width), min(clip[3], y+node.height))
                for child, (ox, oy) in zip(getattr(node, "children", ()),
                        getattr(node, "offsets", ())):
                    found = walk(child, x+ox, y+oy, clip)
                    if found is not None:
                        return found
                return None

            return walk(screen.child, 0, 0, (0, 0, config.screen_width, config.screen_height))

        def render(self, width, height, st, at):
            result = renpy.Render(width, height)
            location = self.locate()
            if location is None:
                return result
            child = renpy.render(self.rope, width, height, st, at)
            x, y, (left, top, right, bottom) = location
            w, h = child.get_size()
            if x+w <= left or x >= right or y+h <= top or y >= bottom:
                self.release()
                return result
            result.blit(child, (x, y))
            if self.rope.active:
                renpy.redraw(self, 1.0/60.0)
            else:
                # Resting text respects the viewport edge; stretched text can
                # cross it while the card is visible.
                clipped = renpy.Render(width, height)
                clipped.blit(result.subsurface((left, top, right-left, bottom-top)), (left, top))
                result = clipped
            return result

        def event(self, ev, x, y, st):
            # Header buttons take priority even if foreground rope glyphs
            # have stretched across their position.
            if self.control_hovered:
                return None
            location = self.locate()
            if location is None:
                return None
            ox, oy, (left, top, right, bottom) = location
            w, h = self.rope.line_size
            if ox+w <= left or ox >= right or oy+h <= top or oy >= bottom:
                self.release()
                return None
            if not self.rope.active and not (left <= x < right and top <= y < bottom):
                return None
            try:
                return self.rope.event(ev, x-ox, y-oy, st)
            finally:
                if self.rope.active:
                    renpy.redraw(self, 0)

screen lintools_demo_gallery():
    default shatter_preview = lintools_text.ReplayableShatterText(lintools_demo_cards[4][1], size=48, color="#ffffff")
    default rope_preview = LinToolsGalleryRope(lintools_demo_rope_source)
    default curtain_preview = lintools_text.CurtainText(lintools_demo_curtain_source, size=48, subdivisions=8)
    default gallery_scroll = ui.adjustment(changed=rope_preview.scrolled)
    on "show" action Show("lintools_rope", rope=rope_preview)
    on "hide" action Hide("lintools_rope")
    modal True
    add Solid("#101823")
    frame:
        background None
        xfill True
        yfill True
        padding (100, 60, 100, 60)
        viewport:
            id "gallery_viewport"
            yfill True
            mousewheel True
            # Viewport records a drag before dispatching to its buttons.
            draggable (not rope_preview.control_hovered)
            scrollbars "vertical"
            yadjustment gallery_scroll
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
                                ysize 48
                                text title size 32 color "#75dccb" yalign 0.5
                                if title == "05 / 破碎":
                                    textbutton "重播":
                                        hovered Function(rope_preview.hover_control, True, _update_screens=False)
                                        unhovered Function(rope_preview.hover_control, False, _update_screens=False)
                                        xalign 1.0
                                        yalign 0.5
                                        text_size 28
                                        # Replay redraws its own displayable; keep the gallery layout.
                                        action Function(shatter_preview.replay, _update_screens=False)
                                elif title == "06 / 弹力绳":
                                    textbutton "复位":
                                        hovered Function(rope_preview.hover_control, True, _update_screens=False)
                                        unhovered Function(rope_preview.hover_control, False, _update_screens=False)
                                        xalign 1.0
                                        yalign 0.5
                                        text_size 28
                                        action Function(rope_preview.reset, _update_screens=False)
                                elif title == "07 / 帘幕":
                                    textbutton "复位":
                                        hovered Function(rope_preview.hover_control, True, _update_screens=False)
                                        unhovered Function(rope_preview.hover_control, False, _update_screens=False)
                                        xalign 1.0
                                        yalign 0.5
                                        text_size 28
                                        action Function(curtain_preview.reset, _update_screens=False)
                            # Flatten each padded effect area before the
                            # viewport recursively crops its moving glyphs.
                            if title == "05 / 破碎":
                                # Reserve space inside the viewport, including
                                # upward kicks and the shards' downward flight.
                                frame:
                                    at Transform(mesh=True)
                                    background None
                                    xfill True
                                    padding (96, 48, 96, 240)
                                    add shatter_preview
                            elif title == "04 / 交互水波":
                                text "上下划过文字，轻触微漾，快速穿过激起波浪。" size 24 color "#8ea7ae"
                                frame:
                                    at Transform(mesh=True)
                                    background None
                                    xfill True
                                    padding (0, 56)
                                    text sample size 48 color "#ffffff" slow_cps 0
                            elif title == "06 / 弹力绳":
                                text "首尾固定，拖动中间的字，松开后回弹晃动。" size 24 color "#8ea7ae"
                                fixed:
                                    ysize 240
                                    add rope_preview.slot yalign 0.5
                            elif title == "07 / 帘幕":
                                text "划过细绳拨动文字，静止后逐渐停下。" size 24 color "#8ea7ae"
                                frame:
                                    at Transform(mesh=True)
                                    background None
                                    xfill True
                                    padding (0, 0)
                                    add curtain_preview xalign 0.5 zoom 0.75
                            else:
                                # A minimum height only adds space below the
                                # text. Padding also protects upward motion.
                                frame:
                                    at Transform(mesh=True)
                                    background None
                                    xfill True
                                    padding (24, 24)
                                    text sample size 48 color "#ffffff" slow_cps 0:
                                        outlines [(1, "#080e16", 0, 0)]
                            text sample.replace("\n", "\\n").replace("{", "{{") substitute False size 22 color "#b5c9dc"

label start:
    scene expression Solid("#101823")
    window hide
    call screen lintools_demo_gallery
    if _return == "interactive":
        jump lintools_demo_interactive
    jump lintools_demo_dialogue

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
