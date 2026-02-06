#!/usr/bin/env python3
"""
Ubuntu图片裁剪工具
支持：拖拽选择区域、调整大小、旋转、批量处理、多种格式导出
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import cairo
import os
import sys
from PIL import Image, ImageDraw, ImageOps
import numpy as np
from datetime import datetime
from math import sqrt, atan2, degrees

class ImageCropper(Gtk.Window):
    def __init__(self):
        super().__init__(title="ImageCropper v1.0")
        
        # 初始化变量
        self.original_image = None
        self.display_image = None
        self.scale_factor = 1.0
        self.crop_rect = None  # (x1, y1, x2, y2) 相对于显示图像
        self.dragging = False
        self.drag_mode = None  # 'move', 'resize_tl', 'resize_tr', 'resize_bl', 'resize_br'
        self.drag_start = (0, 0)
        self.image_path = None
        self.rotation = 0
        self.aspect_ratio = None  # (width, height) 比例，None表示自由比例
        
        # 设置窗口
        self.set_default_size(1000, 700)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # 创建主布局
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add(self.main_box)
        
        # 左侧面板：图像显示区域
        self.create_image_panel()
        
        # 右侧面板：控制区域
        self.create_control_panel()
        
        # 连接信号
        self.connect("destroy", Gtk.main_quit)
        
        # 加载默认主题
        self.apply_theme()
    
    def create_image_panel(self):
        """创建图像显示面板"""
        # 滚动窗口，用于大图像
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        # 绘图区域
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_size_request(600, 600)
        
        # 事件连接
        self.drawing_area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.KEY_PRESS_MASK
        )
        
        self.drawing_area.connect("draw", self.on_draw)
        self.drawing_area.connect("button-press-event", self.on_button_press)
        self.drawing_area.connect("button-release-event", self.on_button_release)
        self.drawing_area.connect("motion-notify-event", self.on_motion_notify)
        
        # 添加标签提示
        self.info_label = Gtk.Label(label="请打开一张图片（支持 JPG, PNG, BMP, GIF）")
        self.info_label.get_style_context().add_class("info-label")
        
        # 布局
        image_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        image_vbox.pack_start(self.info_label, False, False, 5)
        image_vbox.pack_start(scrolled, True, True, 0)
        
        scrolled.add(self.drawing_area)
        
        self.main_box.pack_start(image_vbox, True, True, 0)
    
    def create_control_panel(self):
        """创建控制面板"""
        control_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        control_vbox.set_size_request(300, -1)
        control_vbox.set_margin_top(20)
        control_vbox.set_margin_bottom(20)
        control_vbox.set_margin_start(10)
        control_vbox.set_margin_end(10)
        
        # 文件操作部分
        file_frame = Gtk.Frame(label="文件操作")
        file_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        file_frame.add(file_box)
        
        # 打开按钮
        open_btn = Gtk.Button(label="打开图片")
        open_btn.connect("clicked", self.on_open_image)
        open_btn.get_style_context().add_class("suggested-action")

        
        # 保存按钮
        self.save_btn = Gtk.Button(label="保存裁剪")
        self.save_btn.connect("clicked", self.on_save_image)
        self.save_btn.set_sensitive(False)
        
        # 文件信息
        self.file_info_label = Gtk.Label(label="未选择文件")
        self.file_info_label.set_line_wrap(True)
        self.file_info_label.set_max_width_chars(30)
        
        file_box.pack_start(open_btn, False, False, 5)
        file_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 5)
        file_box.pack_start(self.save_btn, False, False, 5)
        file_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 5)
        file_box.pack_start(self.file_info_label, False, False, 5)
        
        # 裁剪控制部分
        crop_frame = Gtk.Frame(label="裁剪控制")
        crop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        crop_frame.add(crop_box)
        
        # 宽高显示
        size_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        size_box.pack_start(Gtk.Label(label="宽度:"), False, False, 0)
        self.width_label = Gtk.Label(label="0")
        size_box.pack_start(self.width_label, False, False, 0)
        size_box.pack_start(Gtk.Label(label="px"), False, False, 0)
        size_box.pack_start(Gtk.Label(label="高度:"), False, False, 0)
        self.height_label = Gtk.Label(label="0")
        size_box.pack_start(self.height_label, False, False, 0)
        size_box.pack_start(Gtk.Label(label="px"), False, False, 0)
        
        # 比例锁定
        ratio_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ratio_label = Gtk.Label(label="固定比例:")
        ratio_box.pack_start(ratio_label, False, False, 0)
        
        self.ratio_combo = Gtk.ComboBoxText()
        self.ratio_combo.append_text("自由")
        self.ratio_combo.append_text("1:1 (正方形)")
        self.ratio_combo.append_text("4:3 (标准)")
        self.ratio_combo.append_text("16:9 (宽屏)")
        self.ratio_combo.append_text("3:2 (照片)")
        self.ratio_combo.append_text("2:3 (人像)")
        self.ratio_combo.set_active(0)
        self.ratio_combo.connect("changed", self.on_ratio_changed)
        
        ratio_box.pack_start(self.ratio_combo, True, True, 0)
        
        # 预设尺寸
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        preset_label = Gtk.Label(label="预设尺寸:")
        preset_box.pack_start(preset_label, False, False, 0)
        
        self.preset_combo = Gtk.ComboBoxText()
        self.preset_combo.append_text("自定义")
        self.preset_combo.append_text("1920x1080")
        self.preset_combo.append_text("1280x720")
        self.preset_combo.append_text("150x150")
        self.preset_combo.set_active(0)
        self.preset_combo.connect("changed", self.on_preset_changed)
        
        preset_box.pack_start(self.preset_combo, True, True, 0)
        
        # 旋转控制
        rotate_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rotate_label = Gtk.Label(label="旋转角度:")
        rotate_box.pack_start(rotate_label, False, False, 0)
        
        self.rotate_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 360, 5)
        self.rotate_scale.set_value(0)
        self.rotate_scale.set_digits(0)
        self.rotate_scale.connect("value-changed", self.on_rotate_changed)
        
        rotate_box.pack_start(self.rotate_scale, True, True, 0)
        
        self.rotate_label = Gtk.Label(label="0°")
        rotate_box.pack_start(self.rotate_label, False, False, 0)
        
        # 旋转按钮
        rotate_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        rotate_left_btn = Gtk.Button(label="↺ 左转90°")
        rotate_left_btn.connect("clicked", self.on_rotate_left)
        rotate_right_btn = Gtk.Button(label="↻ 右转90°")
        rotate_right_btn.connect("clicked", self.on_rotate_right)
        
        rotate_btn_box.pack_start(rotate_left_btn, True, True, 0)
        rotate_btn_box.pack_start(rotate_right_btn, True, True, 0)
        
        crop_box.pack_start(size_box, False, False, 5)
        crop_box.pack_start(ratio_box, False, False, 5)
        crop_box.pack_start(preset_box, False, False, 5)
        crop_box.pack_start(rotate_box, False, False, 5)
        crop_box.pack_start(rotate_btn_box, False, False, 5)
        

        # 输出路径
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        path_label = Gtk.Label(label="保存路径:")
        path_box.pack_start(path_label, False, False, 0)
        
        self.path_entry = Gtk.Entry()
        self.path_entry.set_text(os.path.expanduser("~/Pictures/cropped"))
        path_box.pack_start(self.path_entry, True, True, 0)
        
        browse_btn = Gtk.Button(label="...")
        #browse_btn.connect("clicked", self.on_browse_path)
        path_box.pack_start(browse_btn, False, False, 0)
        

        
        # 添加到主面板
        control_vbox.pack_start(file_frame, False, False, 0)
        control_vbox.pack_start(crop_frame, False, False, 0)

        
        # 帮助文本
        help_label = Gtk.Label(label="使用说明:\n"
                                  "1. 拖拽选择裁剪区域\n"
                                  "2. 拖动边角调整大小\n"
                                  "3. 拖动内部移动区域\n"
                                  "4. 点击保存按钮导出")
        help_label.set_line_wrap(True)
        help_label.get_style_context().add_class("help-text")
        
        control_vbox.pack_start(help_label, False, False, 10)
        
        self.main_box.pack_start(control_vbox, False, False, 0)
    
    def apply_theme(self):
        """应用CSS样式"""
        css = """
        .info-label {
            font-size: 14px;
            font-weight: bold;
            color: #3465a4;
        }
        
        .suggested-action {
            background-color: #4a90d9;
            color: white;
            font-weight: bold;
        }
        
        .help-text {
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            font-size: 12px;
            color: #555;
        }
        
        button {
            padding: 8px;
            border-radius: 4px;
        }
        
        button:hover {
            background-color: #e0e0e0;
        }
        """
        
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css.encode())
        
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    # ========== 事件处理函数 ==========
    
    def on_open_image(self, widget):
        """打开图片文件"""
        dialog = Gtk.FileChooserDialog(
            title="选择图片",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        # 设置过滤器
        filter_image = Gtk.FileFilter()
        filter_image.set_name("图片文件")
        filter_image.add_mime_type("image/jpeg")
        filter_image.add_mime_type("image/png")
        filter_image.add_mime_type("image/bmp")
        filter_image.add_mime_type("image/gif")
        dialog.add_filter(filter_image)
        
        filter_all = Gtk.FileFilter()
        filter_all.set_name("所有文件")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.image_path = dialog.get_filename()
            self.load_image(self.image_path)
        
        dialog.destroy()
    
    def load_image(self, path):
        """加载图片"""
        try:
            # 使用PIL打开图像
            self.original_image = Image.open(path)
            self.display_image = self.original_image.copy()
            
            # 重置旋转和裁剪
            self.rotation = 0
            self.rotate_scale.set_value(0)
            self.crop_rect = None
            self.save_btn.set_sensitive(False)
            
            # 计算缩放比例以适应显示区域
            display_width = self.drawing_area.get_allocated_width()
            display_height = self.drawing_area.get_allocated_height()
            
            img_width, img_height = self.display_image.size
            
            # 计算缩放比例，保持纵横比
            scale_x = display_width / img_width
            scale_y = display_height / img_height
            self.scale_factor = min(scale_x, scale_y, 1.0)  # 最大放大到原始尺寸
            
            # 更新文件信息
            file_info = f"文件: {os.path.basename(path)}\n"
            file_info += f"尺寸: {img_width} × {img_height} px\n"
            file_info += f"格式: {self.display_image.format}\n"
            file_info += f"模式: {self.display_image.mode}"
            self.file_info_label.set_text(file_info)
            
            # 更新提示
            self.info_label.set_text("拖拽选择裁剪区域")
            
            # 重绘画布
            self.drawing_area.queue_draw()
            
        except Exception as e:
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=0,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text=f"无法打开图片: {str(e)}"
            )
            dialog.run()
            dialog.destroy()
    
    def on_draw(self, widget, cr):
        """绘制图像和裁剪框"""
        # 清除背景
        cr.set_source_rgb(0.9, 0.9, 0.9)
        cr.paint()
        
        if self.display_image is None:
            return
        
        # 计算图像在画布中的位置（居中）
        img_width, img_height = self.display_image.size
        display_width = img_width * self.scale_factor
        display_height = img_height * self.scale_factor
        
        alloc = widget.get_allocation()
        x_offset = (alloc.width - display_width) / 2
        y_offset = (alloc.height - display_height) / 2
        
        # 将图像转换为RGBA格式（cairo需要）
        if self.display_image.mode != 'RGBA':
            # JPG通常是RGB格式，需要转换为RGBA
            rgba_image = self.display_image.convert('RGBA')
        else:
            rgba_image = self.display_image
        
        # 获取RGBA格式的图像数据
        img_data = rgba_image.tobytes()
        
        # 创建cairo图像表面
        # cairo.FORMAT_ARGB32期望每像素4字节（BGRA或ARGB，取决于平台）
        # 但PIL的RGBA是每像素4字节，顺序是R,G,B,A
        # 我们需要进行字节顺序转换
        import struct
        import numpy as np
        
        # 方法1：使用numpy转换（如果可用，推荐）
        # 将字节数据转换为numpy数组
        np_data = np.frombuffer(img_data, dtype=np.uint8)
        np_data = np_data.reshape((img_height, img_width, 4))
        
        # 重新排列通道：从RGBA转换为BGRA（cairo期望的格式）
        # 注意：在little-endian系统上，cairo的ARGB32实际上是BGRA顺序
        bgra_data = np.zeros((img_height, img_width, 4), dtype=np.uint8)
        bgra_data[:, :, 0] = np_data[:, :, 2]  # B
        bgra_data[:, :, 1] = np_data[:, :, 1]  # G
        bgra_data[:, :, 2] = np_data[:, :, 0]  # R
        bgra_data[:, :, 3] = np_data[:, :, 3]  # A
        
        # 将numpy数组转换回字节
        img_data = bgra_data.tobytes()
        
        # 创建cairo图像表面
        stride = cairo.ImageSurface.format_stride_for_width(
            cairo.FORMAT_ARGB32, img_width)
        
        surface = cairo.ImageSurface.create_for_data(
            bytearray(img_data),
            cairo.FORMAT_ARGB32,
            img_width,
            img_height,
            stride
        )
        
        # 缩放并绘制图像
        cr.save()
        cr.translate(x_offset, y_offset)
        cr.scale(self.scale_factor, self.scale_factor)
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        cr.restore()

 # 绘制裁剪框（如果存在）
        if self.crop_rect:
            x1, y1, x2, y2 = self.crop_rect
            
            # 转换为显示坐标
            display_x1 = x1 * self.scale_factor + x_offset
            display_y1 = y1 * self.scale_factor + y_offset
            display_x2 = x2 * self.scale_factor + x_offset
            display_y2 = y2 * self.scale_factor + y_offset
            
            width = display_x2 - display_x1
            height = display_y2 - display_y1
            
            # 绘制半透明覆盖层
            cr.set_source_rgba(0, 0, 0, 0.4)
            cr.rectangle(0, 0, alloc.width, alloc.height)
            cr.rectangle(display_x1, display_y1, width, height)
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()
            
            # 绘制裁剪框边界
            cr.set_line_width(2)
            cr.set_source_rgb(1, 1, 1)
            cr.rectangle(display_x1, display_y1, width, height)
            cr.stroke()
            
            # 绘制控制点
            point_size = 8
            points = [
                (display_x1, display_y1),  # 左上
                (display_x2, display_y1),  # 右上
                (display_x1, display_y2),  # 左下
                (display_x2, display_y2)   # 右下
            ]
            
            cr.set_source_rgb(0, 0.5, 1)
            for px, py in points:
                cr.rectangle(px - point_size/2, py - point_size/2, 
                           point_size, point_size)
                cr.fill()
            
            # 更新尺寸显示
            actual_width =round(abs(x2 - x1),2)
            actual_height = round(abs(y2 - y1),2)
            self.width_label.set_text(str(actual_width))
            self.height_label.set_text(str(actual_height))
    
    def on_button_press(self, widget, event):
        """鼠标按下事件"""
        if self.display_image is None:
            return False
        
        # 计算图像在画布中的位置
        img_width, img_height = self.display_image.size
        display_width = img_width * self.scale_factor
        display_height = img_height * self.scale_factor
        
        alloc = widget.get_allocation()
        x_offset = (alloc.width - display_width) / 2
        y_offset = (alloc.height - display_height) / 2
        
        # 转换为图像坐标
        img_x = (event.x - x_offset) / self.scale_factor
        img_y = (event.y - y_offset) / self.scale_factor
        
        # 检查是否在图像范围内
        if not (0 <= img_x < img_width and 0 <= img_y < img_height):
            return False
        
        if event.button == 1:  # 左键
            if self.crop_rect:
                x1, y1, x2, y2 = self.crop_rect
                
                # 检查点击位置
                margin = 10 / self.scale_factor  # 控制点检测范围
                
                # 检查是否在控制点上
                if abs(img_x - x1) < margin and abs(img_y - y1) < margin:
                    self.drag_mode = 'resize_tl'
                elif abs(img_x - x2) < margin and abs(img_y - y1) < margin:
                    self.drag_mode = 'resize_tr'
                elif abs(img_x - x1) < margin and abs(img_y - y2) < margin:
                    self.drag_mode = 'resize_bl'
                elif abs(img_x - x2) < margin and abs(img_y - y2) < margin:
                    self.drag_mode = 'resize_br'
                # 检查是否在裁剪框内部
                elif (x1 < img_x < x2 and y1 < img_y < y2):
                    self.drag_mode = 'move'
                else:
                    # 开始新的裁剪框
                    self.crop_rect = [img_x, img_y, img_x, img_y]
                    self.drag_mode = 'create'
            else:
                # 开始新的裁剪框
                self.crop_rect = [img_x, img_y, img_x, img_y]
                self.drag_mode = 'create'
            
            self.dragging = True
            self.drag_start = (img_x, img_y)
            self.save_btn.set_sensitive(False)
            return True
        
        return False
    
    def on_button_release(self, widget, event):
        """鼠标释放事件"""
        if event.button == 1 and self.dragging:
            self.dragging = False
            self.drag_mode = None
            
            if self.crop_rect:
                # 确保坐标顺序（左上到右下）
                x1, y1, x2, y2 = self.crop_rect
                self.crop_rect = [
                    min(x1, x2), min(y1, y2),
                    max(x1, x2), max(y1, y2)
                ]
                
                # 更新保存按钮状态
                width = abs(x2 - x1)
                height = abs(y2 - y1)
                if width > 10 and height > 10:  # 最小尺寸
                    self.save_btn.set_sensitive(True)
            
            return True
        return False
    
    def on_motion_notify(self, widget, event):
        """鼠标移动事件"""
        if not self.dragging or self.display_image is None:
            return False
        
        # 计算图像在画布中的位置
        img_width, img_height = self.display_image.size
        display_width = img_width * self.scale_factor
        display_height = img_height * self.scale_factor
        
        alloc = widget.get_allocation()
        x_offset = (alloc.width - display_width) / 2
        y_offset = (alloc.height - display_height) / 2
        
        # 转换为图像坐标
        img_x = (event.x - x_offset) / self.scale_factor
        img_y = (event.y - y_offset) / self.scale_factor
        
        # 限制在图像范围内
        img_x = max(0, min(img_x, img_width))
        img_y = max(0, min(img_y, img_height))
        
        if self.drag_mode == 'create':
            # 创建新的裁剪框
            self.crop_rect[2] = img_x
            self.crop_rect[3] = img_y
            self.apply_aspect_ratio()
        
        elif self.drag_mode == 'move':
            # 移动整个裁剪框
            dx = img_x - self.drag_start[0]
            dy = img_y - self.drag_start[1]
            
            x1, y1, x2, y2 = self.crop_rect
            width = x2 - x1
            height = y2 - y1
            
            # 计算新位置，确保在图像范围内
            new_x1 = max(0, min(x1 + dx, img_width - width))
            new_y1 = max(0, min(y1 + dy, img_height - height))
            
            self.crop_rect = [
                new_x1, new_y1,
                new_x1 + width, new_y1 + height
            ]
            
            self.drag_start = (img_x, img_y)
        
        elif self.drag_mode and self.drag_mode.startswith('resize_'):
            # 调整大小
            x1, y1, x2, y2 = self.crop_rect
            
            if 'tl' in self.drag_mode:
                x1 = img_x
                y1 = img_y
            if 'tr' in self.drag_mode:
                x2 = img_x
                y1 = img_y
            if 'bl' in self.drag_mode:
                x1 = img_x
                y2 = img_y
            if 'br' in self.drag_mode:
                x2 = img_x
                y2 = img_y
            
            self.crop_rect = [x1, y1, x2, y2]
            self.apply_aspect_ratio()
        
        # 重绘画布
        widget.queue_draw()
        return True
    
    def apply_aspect_ratio(self):
        """应用纵横比限制 - 修复边界问题"""
        if self.aspect_ratio is None or self.crop_rect is None or self.display_image is None:
            return
        
        # 获取图像尺寸
        img_width, img_height = self.display_image.size
        
        x1, y1, x2, y2 = self.crop_rect
        target_ratio = self.aspect_ratio[0] / self.aspect_ratio[1]
        
        # 确保坐标顺序（左上到右下）
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        # 当前尺寸
        current_width = max(x2 - x1,1)
        current_height = max(y2 - y1,1)

        
        # 根据拖动模式确定固定角
        if self.drag_mode is None:
            # 如果没有拖动模式，默认固定左上角
            fixed_corner = 'top-left'
        elif 'tl' in self.drag_mode:
            fixed_corner = 'top-left'
        elif 'tr' in self.drag_mode:
            fixed_corner = 'top-right'
        elif 'bl' in self.drag_mode:
            fixed_corner = 'bottom-left'
        elif 'br' in self.drag_mode:
            fixed_corner = 'bottom-right'
        elif 'move' in self.drag_mode:
            fixed_corner = 'center'  # 移动时保持中心不变
        else:
            fixed_corner = 'top-left'  # 默认
        
        # 根据固定角调整裁剪框
        if fixed_corner == 'top-left':
            # 固定左上角，调整右下角
            if current_width / current_height > target_ratio:
                # 太宽，调整高度
                new_height = current_width / target_ratio
                y2 = y1 + new_height
            else:
                # 太高，调整宽度
                new_width = current_height * target_ratio
                x2 = x1 + new_width
            
            # 边界检查：确保右下角不超出图像
            if x2 > img_width:
                x2 = img_width
                # 根据新宽度调整高度以保持比例
                new_height = (x2 - x1) / target_ratio
                y2 = y1 + new_height
            
            if y2 > img_height:
                y2 = img_height
                # 根据新高度调整宽度以保持比例
                new_width = (y2 - y1) * target_ratio
                x2 = x1 + new_width
            
            # 如果调整后左上角超出了边界，需要整体移动
            if x1 < 0 or y1 < 0:
                # 向右下移动
                if x1 < 0:
                    shift = -x1
                    x1 += shift
                    x2 += shift
                
                if y1 < 0:
                    shift = -y1
                    y1 += shift
                    y2 += shift
                
                # 再次检查右下角
                if x2 > img_width:
                    # 需要缩小宽度
                    x2 = img_width
                    new_height = (x2 - x1) / target_ratio
                    y2 = y1 + new_height
                
                if y2 > img_height:
                    y2 = img_height
                    new_width = (y2 - y1) * target_ratio
                    x2 = x1 + new_width
        
        elif fixed_corner == 'top-right':
            # 固定右上角，调整左下角
            if current_width / current_height > target_ratio:
                # 太宽，调整高度
                new_height = current_width / target_ratio
                y2 = y1 + new_height
            else:
                # 太高，调整宽度
                new_width = current_height * target_ratio
                x1 = x2 - new_width
            
            # 边界检查
            if x1 < 0:
                x1 = 0
                new_height = (x2 - x1) / target_ratio
                y2 = y1 + new_height
            
            if y2 > img_height:
                y2 = img_height
                new_width = (y2 - y1) * target_ratio
                x1 = x2 - new_width
            
            # 检查右上角
            if x2 > img_width or y1 < 0:
                if x2 > img_width:
                    shift = x2 - img_width
                    x1 -= shift
                    x2 -= shift
                
                if y1 < 0:
                    shift = -y1
                    y1 += shift
                    y2 += shift
                
                # 再次检查
                if x1 < 0:
                    x1 = 0
                    new_height = (x2 - x1) / target_ratio
                    y2 = y1 + new_height
        
        elif fixed_corner == 'bottom-left':
            # 固定左下角，调整右上角
            if current_width / current_height > target_ratio:
                # 太宽，调整高度
                new_height = current_width / target_ratio
                y1 = y2 - new_height
            else:
                # 太高，调整宽度
                new_width = current_height * target_ratio
                x2 = x1 + new_width
            
            # 边界检查
            if x2 > img_width:
                x2 = img_width
                new_height = (x2 - x1) / target_ratio
                y1 = y2 - new_height
            
            if y1 < 0:
                y1 = 0
                new_width = (y2 - y1) * target_ratio
                x2 = x1 + new_width
            
            # 检查左下角
            if x1 < 0 or y2 > img_height:
                if x1 < 0:
                    shift = -x1
                    x1 += shift
                    x2 += shift
                
                if y2 > img_height:
                    shift = y2 - img_height
                    y1 -= shift
                    y2 -= shift
                
                # 再次检查
                if x2 > img_width:
                    x2 = img_width
                    new_height = (x2 - x1) / target_ratio
                    y1 = y2 - new_height
        
        elif fixed_corner == 'bottom-right':
            # 固定右下角，调整左上角
            if current_width / current_height > target_ratio:
                # 太宽，调整高度
                new_height = current_width / target_ratio
                y1 = y2 - new_height
            else:
                # 太高，调整宽度
                new_width = current_height * target_ratio
                x1 = x2 - new_width
            
            # 边界检查
            if x1 < 0:
                x1 = 0
                new_height = (x2 - x1) / target_ratio
                y1 = y2 - new_height
            
            if y1 < 0:
                y1 = 0
                new_width = (y2 - y1) * target_ratio
                x1 = x2 - new_width
            
            # 检查右下角
            if x2 > img_width or y2 > img_height:
                if x2 > img_width:
                    shift = x2 - img_width
                    x1 -= shift
                    x2 -= shift
                
                if y2 > img_height:
                    shift = y2 - img_height
                    y1 -= shift
                    y2 -= shift
                
                # 再次检查
                if x1 < 0:
                    x1 = 0
                    new_height = (x2 - x1) / target_ratio
                    y1 = y2 - new_height
        
        elif fixed_corner == 'center':
            # 保持中心不变，调整四个边
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            if current_width / current_height > target_ratio:
                # 太宽，调整高度
                new_height = current_width / target_ratio
                y1 = center_y - new_height / 2
                y2 = center_y + new_height / 2
            else:
                # 太高，调整宽度
                new_width = current_height * target_ratio
                x1 = center_x - new_width / 2
                x2 = center_x + new_width / 2
            
            # 边界检查
            if x1 < 0:
                shift = -x1
                x1 += shift
                x2 += shift
            
            if x2 > img_width:
                shift = x2 - img_width
                x1 -= shift
                x2 -= shift
            
            if y1 < 0:
                shift = -y1
                y1 += shift
                y2 += shift
            
            if y2 > img_height:
                shift = y2 - img_height
                y1 -= shift
                y2 -= shift
            
            # 如果移动后仍然超出，需要缩小
            if x1 < 0 or x2 > img_width or y1 < 0 or y2 > img_height:
                # 缩小到适合图像
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(img_width, x2)
                y2 = min(img_height, y2)
                
                # 根据实际尺寸和比例调整
                actual_width = x2 - x1
                actual_height = y2 - y1
                
                if actual_width / actual_height > target_ratio:
                    # 太宽，调整高度
                    new_height = actual_width / target_ratio
                    if new_height > img_height:
                        # 如果还是太高，缩小宽度
                        new_width = img_height * target_ratio
                        x1 = center_x - new_width / 2
                        x2 = center_x + new_width / 2
                        y1 = 0
                        y2 = img_height
                    else:
                        # 调整高度
                        y1 = center_y - new_height / 2
                        y2 = center_y + new_height / 2
                else:
                    # 太高，调整宽度
                    new_width = actual_height * target_ratio
                    if new_width > img_width:
                        # 如果还是太宽，缩小高度
                        new_height = img_width / target_ratio
                        x1 = 0
                        x2 = img_width
                        y1 = center_y - new_height / 2
                        y2 = center_y + new_height / 2
                    else:
                        # 调整宽度
                        x1 = center_x - new_width / 2
                        x2 = center_x + new_width / 2
        
        # 最终边界检查
        x1 = max(0, min(x1, img_width - 1))
        y1 = max(0, min(y1, img_height - 1))
        x2 = max(1, min(x2, img_width))
        y2 = max(1, min(y2, img_height))
        
        # 确保有效尺寸
        if x2 - x1 < 10 or y2 - y1 < 10:
            # 如果太小，使用最小尺寸
            min_size = 20
            if target_ratio >= 1:
                # 宽度 >= 高度
                new_width = min_size
                new_height = new_width / target_ratio
            else:
                # 高度 > 宽度
                new_height = min_size
                new_width = new_height * target_ratio
            
            # 根据固定角放置
            if fixed_corner == 'top-left':
                x2 = min(img_width, x1 + new_width)
                y2 = min(img_height, y1 + new_height)
            elif fixed_corner == 'top-right':
                x1 = max(0, x2 - new_width)
                y2 = min(img_height, y1 + new_height)
            elif fixed_corner == 'bottom-left':
                x2 = min(img_width, x1 + new_width)
                y1 = max(0, y2 - new_height)
            elif fixed_corner == 'bottom-right':
                x1 = max(0, x2 - new_width)
                y1 = max(0, y2 - new_height)
            else:  # center
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                x1 = max(0, center_x - new_width / 2)
                x2 = min(img_width, x1 + new_width)
                y1 = max(0, center_y - new_height / 2)
                y2 = min(img_height, y1 + new_height)
        
        self.crop_rect = [x1, y1, x2, y2]
    
    def on_ratio_changed(self, widget):
        ratio_text = widget.get_active_text()
        ratios = {
            "自由": None,
            "1:1 (正方形)": (1, 1),
            "4:3 (标准)": (4, 3),
            "16:9 (宽屏)": (16, 9),
            "3:2 (照片)": (3, 2),
            "2:3 (人像)": (2, 3)
        }
        self.aspect_ratio = ratios[ratio_text]
        
        # 如果没有图像或没有裁剪框，直接返回
        if self.display_image is None or self.crop_rect is None:
            return
        
        # 获取图像尺寸
        img_width, img_height = self.display_image.size
        
        # 如果已有裁剪框，应用新的比例
        if self.crop_rect and self.aspect_ratio:
            x1, y1, x2, y2 = self.crop_rect
            
            # 确保坐标顺序（左上到右下）
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            
            # 计算当前中心点（用于保持位置）
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # 获取当前尺寸
            current_width = max(x2 - x1,1)
            current_height = max(y2 - y1,1)
            
            # 目标宽高比
            target_ratio = self.aspect_ratio[0] / self.aspect_ratio[1]
            
            # 根据当前尺寸和目标比例计算新尺寸
            # 保持面积大致相同，或者保持宽度/高度中的一个
            if current_width / current_height > target_ratio:
                # 当前太宽，调整高度
                new_height = current_width / target_ratio
                new_width = current_width
            else:
                # 当前太高，调整宽度
                new_width = current_height * target_ratio
                new_height = current_height
            
            # 确保最小尺寸
            min_size = 10
            if new_width < min_size:
                new_width = min_size
                new_height = new_width / target_ratio
            
            if new_height < min_size:
                new_height = min_size
                new_width = new_height * target_ratio
            
            # 从中心点计算新坐标
            new_x1 = center_x - new_width / 2
            new_y1 = center_y - new_height / 2
            new_x2 = center_x + new_width / 2
            new_y2 = center_y + new_height / 2
            
            # ========== 关键：边界检查 ==========
            # 1. 如果裁剪框超出左边界
            if new_x1 < 0:
                shift = -new_x1
                new_x1 += shift
                new_x2 += shift
            
            # 2. 如果裁剪框超出右边界
            if new_x2 > img_width:
                shift = new_x2 - img_width
                new_x1 -= shift
                new_x2 -= shift
            
            # 3. 如果裁剪框超出上边界
            if new_y1 < 0:
                shift = -new_y1
                new_y1 += shift
                new_y2 += shift
            
            # 4. 如果裁剪框超出下边界
            if new_y2 > img_height:
                shift = new_y2 - img_height
                new_y1 -= shift
                new_y2 -= shift
            
            # 再次检查所有边界（处理双重越界情况）
            # 如果裁剪框仍然太大，调整大小而不是位置
            if new_x1 < 0:
                # 左边界越界，向右移动并缩小宽度
                new_x1 = 0
                new_width = new_x2 - new_x1
                # 根据比例调整高度
                new_height = new_width / target_ratio
                new_y1 = center_y - new_height / 2
                new_y2 = center_y + new_height / 2
            
            if new_x2 > img_width:
                new_x2 = img_width
                new_width = new_x2 - new_x1
                new_height = new_width / target_ratio
                new_y1 = center_y - new_height / 2
                new_y2 = center_y + new_height / 2
            
            if new_y1 < 0:
                new_y1 = 0
                new_height = new_y2 - new_y1
                new_width = new_height * target_ratio
                new_x1 = center_x - new_width / 2
                new_x2 = center_x + new_width / 2
            
            if new_y2 > img_height:
                new_y2 = img_height
                new_height = new_y2 - new_y1
                new_width = new_height * target_ratio
                new_x1 = center_x - new_width / 2
                new_x2 = center_x + new_width / 2
            
            # 最终边界检查（防止缩小后再次越界）
            new_x1 = max(0, min(new_x1, img_width - 1))
            new_y1 = max(0, min(new_y1, img_height - 1))
            new_x2 = max(1, min(new_x2, img_width))
            new_y2 = max(1, min(new_y2, img_height))
            
            # 确保有有效的大小
            if new_x2 - new_x1 < 10 or new_y2 - new_y1 < 10:
                # 如果太小，创建一个默认大小的裁剪框
                default_size = min(100, img_width, img_height)
                new_x1 = max(0, center_x - default_size / 2)
                new_y1 = max(0, center_y - default_size / 2)
                new_x2 = min(img_width, new_x1 + default_size)
                new_y2 = min(img_height, new_y1 + default_size)
                
                # 根据比例调整
                if target_ratio > 1:  # 宽度 > 高度
                    new_width = default_size
                    new_height = new_width / target_ratio
                else:  # 高度 >= 宽度
                    new_height = default_size
                    new_width = new_height * target_ratio
                
                new_x1 = max(0, center_x - new_width / 2)
                new_y1 = max(0, center_y - new_height / 2)
                new_x2 = min(img_width, new_x1 + new_width)
                new_y2 = min(img_height, new_y1 + new_height)
            
            # 更新裁剪框
            self.crop_rect = [new_x1, new_y1, new_x2, new_y2]
            
            # 更新保存按钮状态
            width = abs(new_x2 - new_x1)
            height = abs(new_y2 - new_y1)
            self.save_btn.set_sensitive(width > 10 and height > 10)
            
            # 重绘画布
            self.drawing_area.queue_draw()

    def on_preset_changed(self, widget):
        """预设尺寸改变"""
        preset_text = widget.get_active_text()
        
        if preset_text == "自定义" or self.crop_rect is None:
            return
        
        # 解析尺寸
        import re
        match = re.search(r'(\d+)x(\d+)', preset_text)
        if match:
            target_width = int(match.group(1))
            target_height = int(match.group(2))
            
            # 计算当前裁剪框中心
            x1, y1, x2, y2 = self.crop_rect
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # 设置新的裁剪框（保持中心点）
            new_x1 = center_x - target_width / 2
            new_y1 = center_y - target_height / 2
            new_x2 = center_x + target_width / 2
            new_y2 = center_y + target_height / 2
            
            # 确保在图像范围内
            if self.display_image:
                img_width, img_height = self.display_image.size
                if new_x1 < 0:
                    new_x2 -= new_x1
                    new_x1 = 0
                if new_y1 < 0:
                    new_y2 -= new_y1
                    new_y1 = 0
                if new_x2 > img_width:
                    new_x1 -= (new_x2 - img_width)
                    new_x2 = img_width
                if new_y2 > img_height:
                    new_y1 -= (new_y2 - img_height)
                    new_y2 = img_height
            
            self.crop_rect = [new_x1, new_y1, new_x2, new_y2]
            self.drawing_area.queue_draw()
    
    def on_rotate_changed(self, widget):
        """旋转滑块改变"""
        self.rotation = widget.get_value()
        self.rotate_label.set_text(f"{int(self.rotation)}°")
        
        if self.original_image:
            # 旋转图像
            self.display_image = self.original_image.rotate(
                self.rotation, expand=True, resample=Image.BICUBIC)
            
            # 调整裁剪框（如果有）
            if self.crop_rect:
                # 这里简化处理：旋转时清除裁剪框
                self.crop_rect = None
                self.save_btn.set_sensitive(False)
            
            self.drawing_area.queue_draw()
    
    def on_rotate_left(self, widget):
        """左转90度"""
        if self.original_image:
            self.original_image = self.original_image.rotate(90, expand=True)
            self.display_image = self.original_image.copy()
            self.crop_rect = None
            self.save_btn.set_sensitive(False)
            self.drawing_area.queue_draw()
    
    def on_rotate_right(self, widget):
        """右转90度"""
        if self.original_image:
            self.original_image = self.original_image.rotate(-90, expand=True)
            self.display_image = self.original_image.copy()
            self.crop_rect = None
            self.save_btn.set_sensitive(False)
            self.drawing_area.queue_draw()
    
    def on_save_image(self, widget):
        if not self.crop_rect or not self.display_image:
            return

        # 创建保存对话框
        dialog = Gtk.FileChooserDialog(
            title="保存图片",
            parent=self,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK
        )

        # 设置默认文件名
        default_name = f"cropped_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        dialog.set_current_name(default_name)

        # 添加格式过滤器
        filter_jpg = Gtk.FileFilter()
        filter_jpg.set_name("JPEG 图像 (*.jpg, *.jpeg)")
        filter_jpg.add_pattern("*.jpg")
        filter_jpg.add_pattern("*.jpeg")
        dialog.add_filter(filter_jpg)

        filter_png = Gtk.FileFilter()
        filter_png.set_name("PNG 图像 (*.png)")
        filter_png.add_pattern("*.png")
        dialog.add_filter(filter_png)

        filter_bmp = Gtk.FileFilter()
        filter_bmp.set_name("BMP 图像 (*.bmp)")
        filter_bmp.add_pattern("*.bmp")
        dialog.add_filter(filter_bmp)

        filter_gif = Gtk.FileFilter()
        filter_gif.set_name("GIF 图像 (*.gif)")
        filter_gif.add_pattern("*.gif")
        dialog.add_filter(filter_gif)

        # 显示对话框
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            # 获取用户选择的文件名
            filename = dialog.get_filename()
            # 获取用户选择的过滤器（格式）
            file_filter = dialog.get_filter()

            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                # 从扩展名推断格式
                ext = filename.lower().split('.')[-1]
                if ext in ['jpg', 'jpeg']:
                    output_format = "JPEG"
                elif ext == 'png':
                    output_format = "PNG"
                elif ext == 'bmp':
                    output_format = "BMP"
                elif ext == 'gif':
                    output_format = "GIF"
                else:
                    output_format = "JPEG"  # 默认
            else:
                if file_filter == filter_jpg:
                    output_format = "JPEG"
                    filename = filename + ".jpg"  # 添加扩展名
                elif file_filter == filter_png:
                    output_format = "PNG"
                    filename = filename + ".png"  # 添加扩展名
                elif file_filter == filter_bmp:
                    output_format = "BMP"
                    filename = filename + ".bmp"  # 添加扩展名
                elif file_filter == filter_gif:
                    output_format = "GIF"
                    filename = filename + ".gif"  # 添加扩展名

            # 裁剪图像（与之前相同）
            x1, y1, x2, y2 = map(int, self.crop_rect)
            img_width, img_height = self.display_image.size
            x1 = max(0, min(x1, img_width))
            y1 = max(0, min(y1, img_height))
            x2 = max(0, min(x2, img_width))
            y2 = max(0, min(y2, img_height))
            if x2 <= x1 or y2 <= y1:
                dialog.destroy()
                self.show_error_dialog("无效的裁剪区域")
                return
            cropped = self.display_image.crop((x1, y1, x2, y2))
           

            if output_format == "JPG" or output_format == "JPEG":
                # JPG格式不支持透明度，需要处理
                if cropped.mode in ('RGBA', 'LA') or (cropped.mode == 'P' and 'transparency' in cropped.info):
                    # 方法1：用白色背景填充透明区域（推荐）
                    print(f"检测到透明图像，转换为JPG时用白色背景填充")
                    
                    # 创建白色背景
                    background = Image.new('RGB', cropped.size, (255, 255, 255))
                    
                    if cropped.mode == 'RGBA':
                        # 分离Alpha通道
                        r, g, b, a = cropped.split()
                        # 将RGB通道合并到背景上
                        background.paste(cropped, mask=a)
                    elif cropped.mode == 'LA':
                        # 灰度+透明度
                        cropped = cropped.convert('RGBA')
                        r, g, b, a = cropped.split()
                        background.paste(Image.merge('RGB', (r, g, b)), mask=a)
                    elif cropped.mode == 'P':
                        # 调色板模式
                        cropped = cropped.convert('RGBA')
                        r, g, b, a = cropped.split()
                        background.paste(Image.merge('RGB', (r, g, b)), mask=a)
                    
                    cropped = background
                elif cropped.mode != 'RGB':
                    # 其他非RGB模式转换为RGB
                    cropped = cropped.convert('RGB')
            # 根据选择的格式处理图像并保存
            try:
                # 这里调用之前写的转换和保存逻辑，注意要传递output_format和filename
                cropped.save(filename, format=output_format)
            except Exception as e:
                dialog = Gtk.MessageDialog(
                    parent=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text=f"保存失败: {str(e)}"
                )
        else:
            # 用户取消
            pass

        dialog.destroy()
        
        def on_browse_path(self, widget):
            """浏览保存路径"""
            dialog = Gtk.FileChooserDialog(
                title="选择保存目录",
                parent=self,
                action=Gtk.FileChooserAction.SELECT_FOLDER
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "选择", Gtk.ResponseType.OK
            )
            
            current_path = self.path_entry.get_text()
            if os.path.exists(current_path):
                dialog.set_current_folder(current_path)
            
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                self.path_entry.set_text(dialog.get_filename())
            
            dialog.destroy()


def main():
    # 检查依赖
    try:
        import gi
        from PIL import Image
    except ImportError as e:
        print("缺少依赖，请安装：")
        print("sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0")
        print("pip3 install Pillow")
        return
    
    # 创建并运行应用
    app = ImageCropper()
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
