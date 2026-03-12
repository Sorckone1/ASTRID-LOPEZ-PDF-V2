from copy import copy
from io import BytesIO
import os
import re
import subprocess
import sys
import unicodedata

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation, PageObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from PySide6.QtCore import (
    Qt,
    Signal,
    QSize,
    QSettings,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import (
    QPixmap,
    QFontDatabase,
    QFont,
    QMouseEvent,
    QDragEnterEvent,
    QDropEvent,
    QColor,
    QAction,
    QActionGroup,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
    QMenu,
    QGraphicsOpacityEffect,
)

from ui.styles import APP_STYLES


VALID_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf"
}

PAGE_SIZE_POINTS = {
    "Original": None,
    "A4": (595.28, 841.89),
    "Carta": (612.0, 792.0),
}


def collect_supported_files(paths: list[str]) -> list[str]:
    found = []

    for path in paths:
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    full = os.path.join(root, file)
                    ext = os.path.splitext(full)[1].lower()
                    if ext in VALID_EXTENSIONS:
                        found.append(full)
        else:
            ext = os.path.splitext(path)[1].lower()
            if ext in VALID_EXTENSIONS:
                found.append(path)

    return found


def sanitize_filename(text: str) -> str:
    text = text.strip()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.upper()
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Z0-9_\-\.]", "", text)
    text = re.sub(r"_+", "_", text)
    return text or "SIN_NOMBRE"


def ensure_unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    counter = 2

    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def compression_quality(label: str) -> int:
    if label == "Alta":
        return 95
    if label == "Equilibrada":
        return 82
    return 62


def image_to_pdf_bytes(image_path: str, page_mode: str, compression: str) -> BytesIO:
    with Image.open(image_path) as im:
        im = ImageOps.exif_transpose(im)

        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        elif im.mode == "L":
            im = im.convert("RGB")

        img_w, img_h = im.size

        img_buffer = BytesIO()
        im.save(
            img_buffer,
            format="JPEG",
            quality=compression_quality(compression),
            optimize=True,
        )
        img_buffer.seek(0)

        if page_mode == "Original":
            page_w, page_h = img_w, img_h
            draw_w, draw_h = img_w, img_h
            pos_x, pos_y = 0, 0
        else:
            page_w, page_h = PAGE_SIZE_POINTS[page_mode]
            scale = min(page_w / img_w, page_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
            pos_x = (page_w - draw_w) / 2
            pos_y = (page_h - draw_h) / 2

        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=(page_w, page_h))
        c.drawImage(ImageReader(img_buffer), pos_x, pos_y, width=draw_w, height=draw_h)
        c.showPage()
        c.save()
        pdf_buffer.seek(0)

        return pdf_buffer


def fit_pdf_page(page, page_mode: str):
    if page_mode == "Original":
        return page

    target_w, target_h = PAGE_SIZE_POINTS[page_mode]
    orig_w = float(page.mediabox.width)
    orig_h = float(page.mediabox.height)

    scale = min(target_w / orig_w, target_h / orig_h)
    scaled_w = orig_w * scale
    scaled_h = orig_h * scale
    move_x = (target_w - scaled_w) / 2
    move_y = (target_h - scaled_h) / 2

    new_page = PageObject.create_blank_page(width=target_w, height=target_h)

    page_copy = copy(page)
    page_copy.add_transformation(
        Transformation().scale(scale, scale).translate(move_x, move_y)
    )
    new_page.merge_page(page_copy)
    return new_page


def open_path(path: str):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


class ThumbItem(QFrame):
    clicked = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, path: str, selected: bool = False):
        super().__init__()

        self.path = path
        self.selected = selected

        self.setFixedSize(68, 82)
        self.apply_style()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14 if selected else 10)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(190, 160, 175, 65))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()

        self.close_btn = QToolButton()
        self.close_btn.setText("×")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setStyleSheet("""
            QToolButton {
                background: rgba(255,255,255,0.96);
                border: 1px solid rgba(255,255,255,1);
                border-radius: 8px;
                color: #8F5870;
                font-size: 11px;
                font-weight: 700;
            }
            QToolButton:hover {
                background: rgba(255,245,250,0.98);
                border: 1px solid rgba(241,83,161,0.22);
            }
        """)
        self.close_btn.clicked.connect(lambda: self.removeRequested.emit(self.path))
        top_row.addWidget(self.close_btn)

        layout.addLayout(top_row)

        preview_wrap = QFrame()
        preview_wrap.setFixedHeight(34)
        preview_wrap.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.76),
                stop:1 rgba(255,255,255,0.48)
            );
            border-radius: 9px;
            border: none;
        """)

        preview_layout = QVBoxLayout(preview_wrap)
        preview_layout.setContentsMargins(2, 2, 2, 2)
        preview_layout.setSpacing(0)

        ext = os.path.splitext(path)[1].lower()

        if ext == ".pdf":
            preview = QLabel("PDF")
            preview.setAlignment(Qt.AlignCenter)
            preview.setStyleSheet("""
                color: #8F5870;
                font-size: 10px;
                font-weight: 700;
                background: transparent;
                border: none;
            """)
        else:
            preview = QLabel()
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                preview.setPixmap(pix)
            preview.setAlignment(Qt.AlignCenter)
            preview.setStyleSheet("background: transparent; border: none;")

        preview_layout.addWidget(preview)

        file_name = os.path.basename(path)
        if len(file_name) > 10:
            file_name = file_name[:7] + "..."

        file_label = QLabel(file_name)
        file_label.setAlignment(Qt.AlignCenter)
        file_label.setStyleSheet("""
            color: rgba(97,67,82,0.84);
            font-size: 8px;
            background: transparent;
            border: none;
        """)

        layout.addWidget(preview_wrap)
        layout.addWidget(file_label)

    def apply_style(self):
        if self.selected:
            self.setStyleSheet("""
                QFrame {
                    background: rgba(255,255,255,0.96);
                    border: 2px solid rgba(241,83,161,0.80);
                    border-radius: 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: rgba(255,255,255,0.86);
                    border: 1px solid rgba(255,255,255,0.98);
                    border-radius: 14px;
                }
            """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.path)
        super().mousePressEvent(event)


class DragListWidget(QListWidget):
    orderChanged = Signal(list)
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()

        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.Adjust)
        self.setSpacing(8)
        self.setMovement(QListWidget.Snap)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setHorizontalScrollMode(QListWidget.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.viewport().setAcceptDrops(True)

        self.setSelectionMode(QListWidget.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)

        self.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item:selected {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                background: transparent;
                border: none;
                outline: none;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 8px;
                margin: 0px 8px 0px 8px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(143,88,112,0.34);
                border-radius: 4px;
                min-width: 24px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(143,88,112,0.48);
            }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.source() == self:
            event.acceptProposedAction()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.source() == self or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.source() == self:
            super().dropEvent(event)
            self.orderChanged.emit(self.current_paths())
            return

        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
            if paths:
                self.filesDropped.emit(paths)
                event.acceptProposedAction()
                return

        event.ignore()

    def current_paths(self):
        paths = []
        for i in range(self.count()):
            item = self.item(i)
            paths.append(item.data(Qt.UserRole))
        return paths


class UploadArea(QFrame):
    clicked = Signal()
    filesDropped = Signal(list)
    orderChanged = Signal(list)

    def __init__(self):
        super().__init__()

        self.setObjectName("UploadCard")
        self.setAcceptDrops(True)
        self.setFixedHeight(168)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(0)

        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(0)

        self.badge = QLabel("+")
        self.badge.setObjectName("UploadBadge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(60, 60)

        badge_wrap = QHBoxLayout()
        badge_wrap.addStretch()
        badge_wrap.addWidget(self.badge)
        badge_wrap.addStretch()

        self.title = QLabel("Agregar archivos")
        self.title.setObjectName("UploadTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.subtitle = QLabel("Arrastra imágenes, PDFs o carpetas")
        self.subtitle.setObjectName("UploadSubtext")
        self.subtitle.setAlignment(Qt.AlignCenter)

        self.helper = QLabel("O usa el botón de abajo")
        self.helper.setObjectName("UploadCount")
        self.helper.setAlignment(Qt.AlignCenter)

        empty_layout.addStretch()
        empty_layout.addLayout(badge_wrap)
        empty_layout.addSpacing(8)
        empty_layout.addWidget(self.title)
        empty_layout.addSpacing(2)
        empty_layout.addWidget(self.subtitle)
        empty_layout.addSpacing(2)
        empty_layout.addWidget(self.helper)
        empty_layout.addStretch()

        self.list_widget = DragListWidget()
        self.list_widget.hide()
        self.list_widget.filesDropped.connect(self.filesDropped.emit)
        self.list_widget.orderChanged.connect(self.orderChanged.emit)

        self.main_layout.addWidget(self.empty_widget)
        self.main_layout.addWidget(self.list_widget)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.empty_widget.isVisible():
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                QFrame#UploadCard {
                    background: rgba(255,255,255,0.46);
                    border: 1px solid rgba(241,83,161,0.36);
                    border-radius: 24px;
                }
            """)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("")
        urls = event.mimeData().urls()
        if not urls:
            return

        paths = []
        for url in urls:
            if url.isLocalFile():
                paths.append(url.toLocalFile())

        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()

    def set_empty_state(self):
        self.empty_widget.show()
        self.list_widget.hide()

    def set_loaded_state(self, total_files: int):
        self.empty_widget.hide()
        self.list_widget.show()

    def rebuild_thumbnails(self, files: list[str], selected_path: str | None, click_handler, remove_handler):
        self.list_widget.clear()

        for path in files:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            item.setSizeHint(QSize(72, 86))

            widget = ThumbItem(path, selected=(path == selected_path))
            widget.clicked.connect(click_handler)
            widget.removeRequested.connect(remove_handler)

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)


class PremiumMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(self.windowFlags() | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(170, 135, 150, 85))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            QMenu {
                background: rgba(255,248,252,0.97);
                border: 1px solid rgba(255,255,255,0.96);
                border-radius: 18px;
                padding: 8px;
                color: #6F5362;
            }
            QMenu::item {
                padding: 8px 18px;
                border-radius: 10px;
                background: transparent;
                margin: 1px 0px;
            }
            QMenu::item:selected {
                background: rgba(241,83,161,0.09);
            }
        """)


class SuccessBanner(QFrame):
    def __init__(self, parent, text):
        super().__init__(parent)

        self.setFixedSize(430, 92)
        self.setStyleSheet("""
            QFrame {
                background: rgba(255,248,252,0.84);
                border: 1px solid rgba(255,255,255,0.92);
                border-radius: 24px;
            }
            QLabel {
                background: transparent;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        icon = QLabel("✓")
        icon.setStyleSheet("""
            font-size: 22px;
            font-weight: 700;
            color: #cf8aac;
            background: rgba(255,255,255,0.82);
            border-radius: 16px;
            padding: 6px 12px;
        """)

        label = QLabel(text)
        label.setStyleSheet("""
            font-size: 15px;
            font-weight: 600;
            color: #7a5a6a;
        """)

        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addStretch()

        gloss = QFrame(self)
        gloss.setGeometry(0, 0, 430, 44)
        gloss.setAttribute(Qt.WA_TransparentForMouseEvents)
        gloss.setStyleSheet("""
            background: qlineargradient(
                x1:0, y1:0,
                x2:0, y2:1,
                stop:0 rgba(255,255,255,0.72),
                stop:1 rgba(255,255,255,0.07)
            );
            border-top-left-radius: 24px;
            border-top-right-radius: 24px;
            border-bottom-left-radius: 0px;
            border-bottom-right-radius: 0px;
        """)
        gloss.lower()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("Sorck", "AstridLopezPDF")

        self.files = []
        self.selected_path = None
        self.output_folder = self.settings.value("output_folder", os.path.expanduser("~/Documents"))
        self.page_mode = self.settings.value("page_mode", "Original")
        self.compression_mode = self.settings.value("compression_mode", "Alta")
        self.last_pdf_path = None

        self.current_banner = None
        self.banner_opacity_effect = None
        self.banner_fade_in = None
        self.banner_fade_out = None

        self.setFixedSize(960, 680)
        self.setWindowTitle("Astrid Lopez")

        self.load_fonts()
        self.setStyleSheet(APP_STYLES)

        root = QWidget()
        root.setObjectName("RootWindow")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(16)

        self.build_top_bar(root_layout)
        self.build_main_card(root_layout)

        self.update_counter()
        self.update_action_buttons()
        self.update_filename_preview()
        self.set_status("Listo para trabajar.")

    def load_fonts(self):
        font_folder = os.path.join(os.getcwd(), "assets", "fonts")
        if not os.path.isdir(font_folder):
            return
        for file in os.listdir(font_folder):
            if file.lower().endswith(".ttf"):
                QFontDatabase.addApplicationFont(os.path.join(font_folder, file))

    def build_top_bar(self, parent_layout):
        title = QLabel("ASTRID LOPEZ")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("TitleLabel")

        font = QFont("Montserrat")
        font.setPointSize(24)
        font.setWeight(QFont.Bold)
        title.setFont(font)

        parent_layout.addWidget(title)

    def build_settings_menu(self):
        menu = PremiumMenu(self)

        page_menu = PremiumMenu(menu)
        page_menu.setTitle("Tamaño de hoja")

        compression_menu = PremiumMenu(menu)
        compression_menu.setTitle("Compresión")

        menu.addMenu(page_menu)
        menu.addMenu(compression_menu)

        self.page_group = QActionGroup(self)
        self.page_group.setExclusive(True)
        self.page_actions = {}

        for label in ["Original", "A4", "Carta"]:
            action = QAction(label, self, checkable=True)
            action.setChecked(label == self.page_mode)
            action.triggered.connect(lambda checked=False, value=label: self.set_page_mode(value))
            self.page_group.addAction(action)
            page_menu.addAction(action)
            self.page_actions[label] = action

        self.compression_group = QActionGroup(self)
        self.compression_group.setExclusive(True)
        self.compression_actions = {}

        for label in ["Alta", "Equilibrada", "Ligera"]:
            action = QAction(label, self, checkable=True)
            action.setChecked(label == self.compression_mode)
            action.triggered.connect(lambda checked=False, value=label: self.set_compression_mode(value))
            self.compression_group.addAction(action)
            compression_menu.addAction(action)
            self.compression_actions[label] = action

        return menu

    def open_settings_menu(self):
        pos = self.config_btn.mapToGlobal(self.config_btn.rect().bottomLeft())
        self.config_menu.exec(pos)

    def build_main_card(self, parent_layout):
        card = QFrame()
        card.setObjectName("MainCard")
        parent_layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 22, 26, 22)
        card_layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.addStretch()

        self.config_btn = QToolButton()
        self.config_btn.setText("⚙")
        self.config_btn.setCursor(Qt.PointingHandCursor)
        self.config_btn.setFixedSize(34, 34)
        self.config_btn.setStyleSheet("""
            QToolButton {
                background: rgba(255,255,255,0.84);
                border: 1px solid rgba(255,255,255,0.96);
                border-radius: 17px;
                color: #8A6073;
                font-size: 16px;
                font-weight: 700;
            }
            QToolButton:hover {
                background: rgba(255,255,255,0.98);
                border: 1px solid rgba(241,83,161,0.18);
            }
            QToolButton:pressed {
                background: rgba(250,243,247,0.98);
            }
            QToolButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)

        config_shadow = QGraphicsDropShadowEffect(self.config_btn)
        config_shadow.setBlurRadius(14)
        config_shadow.setOffset(0, 4)
        config_shadow.setColor(QColor(190, 160, 175, 55))
        self.config_btn.setGraphicsEffect(config_shadow)

        self.config_menu = self.build_settings_menu()
        self.config_btn.clicked.connect(self.open_settings_menu)

        top_row.addWidget(self.config_btn)
        card_layout.addLayout(top_row)

        hero = QLabel("Crear PDF")
        hero.setAlignment(Qt.AlignCenter)
        hero.setObjectName("HeroLabel")

        font = QFont("Montserrat")
        font.setPointSize(20)
        font.setWeight(QFont.DemiBold)
        hero.setFont(font)

        card_layout.addWidget(hero)

        fields_layout = QHBoxLayout()
        fields_layout.setSpacing(12)

        self.patient_input = self.create_field("PACIENTE", "Nombre del paciente")
        self.study_input = self.create_field("ESTUDIO", "Tipo de estudio")

        self.patient_input["line"].textChanged.connect(self.on_form_changed)
        self.study_input["line"].textChanged.connect(self.on_form_changed)

        fields_layout.addWidget(self.patient_input["widget"])
        fields_layout.addWidget(self.study_input["widget"])

        card_layout.addLayout(fields_layout)

        self.upload_area = UploadArea()
        self.upload_area.clicked.connect(self.select_files)
        self.upload_area.filesDropped.connect(self.handle_dropped_paths)
        self.upload_area.orderChanged.connect(self.handle_reordered_paths)
        card_layout.addWidget(self.upload_area)

        toolbar = QFrame()
        toolbar.setObjectName("MiniToolbar")

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(8)

        self.add_files_btn = QPushButton("Agregar archivos")
        self.add_files_btn.setObjectName("SoftButton")
        self.add_files_btn.clicked.connect(self.select_files)

        self.move_left_btn = QPushButton("Mover izquierda")
        self.move_left_btn.setObjectName("SoftButton")
        self.move_left_btn.clicked.connect(self.move_left)

        self.move_right_btn = QPushButton("Mover derecha")
        self.move_right_btn.setObjectName("SoftButton")
        self.move_right_btn.clicked.connect(self.move_right)

        self.clear_btn = QPushButton("Vaciar Todo")
        self.clear_btn.setObjectName("SoftButton")
        self.clear_btn.clicked.connect(self.clear_files)

        self.counter_label = QLabel("0 archivos")
        self.counter_label.setObjectName("SmallMuted")

        toolbar_layout.addWidget(self.add_files_btn)
        toolbar_layout.addWidget(self.move_left_btn)
        toolbar_layout.addWidget(self.move_right_btn)
        toolbar_layout.addWidget(self.clear_btn)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.counter_label)

        card_layout.addWidget(toolbar)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)

        file_bar = QFrame()
        file_bar.setObjectName("BottomBar")
        file_layout = QHBoxLayout(file_bar)
        file_layout.setContentsMargins(14, 9, 14, 9)
        file_layout.setSpacing(8)

        file_icon = QLabel()
        icon_path = os.path.join("assets", "icons", "carpeta.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            file_icon.setPixmap(pixmap)

        self.output_label = QLabel(self.output_folder)
        self.output_label.setObjectName("SmallMuted")

        choose_btn = QPushButton("Cambiar")
        choose_btn.setObjectName("SoftButton")
        choose_btn.clicked.connect(self.select_output_folder)

        file_layout.addWidget(file_icon)
        file_layout.addWidget(self.output_label)
        file_layout.addStretch()
        file_layout.addWidget(choose_btn)

        name_bar = QFrame()
        name_bar.setObjectName("BottomBar")
        name_layout = QHBoxLayout(name_bar)
        name_layout.setContentsMargins(14, 9, 14, 9)
        name_layout.setSpacing(8)

        name_title = QLabel("Archivo final")
        name_title.setObjectName("SmallMuted")

        self.filename_preview_label = QLabel("SIN_NOMBRE_SIN_ESTUDIO.pdf")
        self.filename_preview_label.setObjectName("SmallMuted")
        self.filename_preview_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        name_layout.addWidget(name_title)
        name_layout.addStretch()
        name_layout.addWidget(self.filename_preview_label)

        info_row.addWidget(file_bar, 1)
        info_row.addWidget(name_bar, 1)

        card_layout.addLayout(info_row)

        self.status_label = QLabel("Listo.")
        self.status_label.setObjectName("SmallMuted")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        card_layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        actions.setSpacing(10)

        self.open_folder_btn = QPushButton("Abrir carpeta")
        self.open_folder_btn.setObjectName("SoftButton")
        self.open_folder_btn.clicked.connect(self.open_output_folder)

        self.open_pdf_btn = QPushButton("Abrir PDF")
        self.open_pdf_btn.setObjectName("SoftButton")
        self.open_pdf_btn.clicked.connect(self.open_last_pdf)

        self.create_btn = QPushButton("Crear PDF")
        self.create_btn.setObjectName("PrimaryButton")
        self.create_btn.clicked.connect(self.create_pdf)

        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.open_pdf_btn)
        actions.addStretch()
        actions.addWidget(self.create_btn)

        card_layout.addLayout(actions)

    def set_page_mode(self, value: str):
        self.page_mode = value
        self.settings.setValue("page_mode", value)
        for label, action in self.page_actions.items():
            action.setChecked(label == value)
        self.set_status(f"Tamaño de hoja: {value}")

    def set_compression_mode(self, value: str):
        self.compression_mode = value
        self.settings.setValue("compression_mode", value)
        for label, action in self.compression_actions.items():
            action.setChecked(label == value)
        self.set_status(f"Compresión: {value}")

    def create_field(self, label_text, placeholder):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel(label_text)
        label.setObjectName("SectionLabel")

        label_font = QFont("Montserrat")
        label_font.setPointSize(10)
        label_font.setWeight(QFont.Medium)
        label.setFont(label_font)

        line = QLineEdit()
        line.setPlaceholderText(placeholder)
        line.setFixedHeight(40)

        line_font = QFont("Montserrat")
        line_font.setPointSize(11)
        line.setFont(line_font)

        layout.addWidget(label)
        layout.addWidget(line)

        return {"widget": wrap, "line": line}

    def show_success_banner(self, text: str):
        if self.current_banner:
            self.current_banner.close()
            self.current_banner = None

        banner = SuccessBanner(self.centralWidget(), text)
        shadow = QGraphicsDropShadowEffect(banner)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(180, 140, 160, 110))

        opacity = QGraphicsOpacityEffect(banner)
        opacity.setOpacity(0.0)

        banner.setGraphicsEffect(opacity)

        x = (self.centralWidget().width() - banner.width()) // 2
        y = (self.centralWidget().height() - banner.height()) // 2
        banner.move(x, y)
        banner.show()
        banner.raise_()

        self.current_banner = banner
        self.banner_opacity_effect = opacity

        self.banner_fade_in = QPropertyAnimation(opacity, b"opacity", self)
        self.banner_fade_in.setDuration(220)
        self.banner_fade_in.setStartValue(0.0)
        self.banner_fade_in.setEndValue(1.0)
        self.banner_fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.banner_fade_in.start()

        def fade_out_banner():
            if not self.current_banner:
                return

            banner_to_close = self.current_banner

            self.banner_fade_out = QPropertyAnimation(self.banner_opacity_effect, b"opacity", self)
            self.banner_fade_out.setDuration(240)
            self.banner_fade_out.setStartValue(1.0)
            self.banner_fade_out.setEndValue(0.0)
            self.banner_fade_out.setEasingCurve(QEasingCurve.InOutCubic)

            def cleanup():
                banner_to_close.close()
                if self.current_banner == banner_to_close:
                    self.current_banner = None

            self.banner_fade_out.finished.connect(cleanup)
            self.banner_fade_out.start()

        QTimer.singleShot(1900, fade_out_banner)

    def on_form_changed(self):
        self.update_filename_preview()
        self.update_action_buttons()

    def update_filename_preview(self):
        patient = self.patient_input["line"].text().strip()
        study = self.study_input["line"].text().strip()

        safe_patient = sanitize_filename(patient) if patient else "SIN_NOMBRE"
        safe_study = sanitize_filename(study) if study else "SIN_ESTUDIO"

        self.filename_preview_label.setText(f"{safe_patient}_{safe_study}.pdf")

    def set_status(self, text: str):
        self.status_label.setText(text)

    def on_thumbnail_clicked(self, path: str):
        self.selected_path = path
        self.refresh_thumbnails()
        self.update_action_buttons()

    def on_remove_requested(self, path: str):
        if path in self.files:
            self.files.remove(path)

        if self.selected_path == path:
            self.selected_path = self.files[0] if self.files else None

        self.refresh_thumbnails()
        self.update_counter()
        self.update_action_buttons()
        self.set_status("Archivo eliminado.")

    def handle_reordered_paths(self, paths: list[str]):
        self.files = paths
        if self.selected_path not in self.files:
            self.selected_path = self.files[0] if self.files else None
        self.refresh_thumbnails()
        self.update_action_buttons()
        self.set_status("Orden actualizado.")

    def refresh_thumbnails(self):
        if not self.files:
            self.upload_area.set_empty_state()
            self.selected_path = None
            self.upload_area.list_widget.clear()
            return

        if self.selected_path is None or self.selected_path not in self.files:
            self.selected_path = self.files[0]

        self.upload_area.set_loaded_state(len(self.files))
        self.upload_area.rebuild_thumbnails(
            self.files,
            self.selected_path,
            self.on_thumbnail_clicked,
            self.on_remove_requested
        )

    def update_counter(self):
        total = len(self.files)
        self.counter_label.setText("1 archivo" if total == 1 else f"{total} archivos")

    def update_action_buttons(self):
        has_selection = self.selected_path in self.files if self.selected_path else False
        selected_index = self.files.index(self.selected_path) if has_selection else -1
        has_required_fields = bool(self.patient_input["line"].text().strip() and self.study_input["line"].text().strip())
        has_files = len(self.files) > 0

        self.move_left_btn.setEnabled(has_selection and selected_index > 0)
        self.move_right_btn.setEnabled(has_selection and selected_index < len(self.files) - 1)
        self.clear_btn.setEnabled(has_files)
        self.open_pdf_btn.setEnabled(bool(self.last_pdf_path and os.path.exists(self.last_pdf_path)))
        self.create_btn.setEnabled(has_required_fields and has_files)

    def add_files_from_paths(self, paths: list[str]):
        supported = collect_supported_files(paths)
        if not supported:
            self.set_status("No se encontraron archivos compatibles.")
            return

        added = 0
        for path in supported:
            if path not in self.files:
                self.files.append(path)
                added += 1

        if added > 0:
            if self.selected_path is None:
                self.selected_path = self.files[0]
            self.refresh_thumbnails()
            self.update_counter()
            self.update_action_buttons()
            self.set_status(f"Se agregaron {added} archivo(s).")
        else:
            self.set_status("No se agregaron archivos nuevos.")

    def handle_dropped_paths(self, paths: list[str]):
        self.add_files_from_paths(paths)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Selecciona archivos",
            "",
            "Archivos (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.pdf)"
        )
        if files:
            self.add_files_from_paths(files)

    def move_left(self):
        if self.selected_path not in self.files:
            return
        idx = self.files.index(self.selected_path)
        if idx <= 0:
            return

        self.files[idx - 1], self.files[idx] = self.files[idx], self.files[idx - 1]
        self.refresh_thumbnails()
        self.update_action_buttons()
        self.set_status("Archivo movido a la izquierda.")

    def move_right(self):
        if self.selected_path not in self.files:
            return
        idx = self.files.index(self.selected_path)
        if idx >= len(self.files) - 1:
            return

        self.files[idx + 1], self.files[idx] = self.files[idx], self.files[idx + 1]
        self.refresh_thumbnails()
        self.update_action_buttons()
        self.set_status("Archivo movido a la derecha.")

    def clear_files(self):
        self.files = []
        self.selected_path = None
        self.upload_area.list_widget.clear()
        self.upload_area.set_empty_state()
        self.update_counter()
        self.update_action_buttons()
        self.set_status("Se vació la lista de archivos.")

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecciona carpeta de salida",
            self.output_folder
        )
        if folder:
            self.output_folder = folder
            self.settings.setValue("output_folder", folder)
            self.output_label.setText(folder)
            self.set_status("Carpeta de salida actualizada.")

    def open_output_folder(self):
        if self.output_folder and os.path.isdir(self.output_folder):
            open_path(self.output_folder)
            self.set_status("Abriendo carpeta de salida.")

    def open_last_pdf(self):
        if self.last_pdf_path and os.path.exists(self.last_pdf_path):
            open_path(self.last_pdf_path)
            self.set_status("Abriendo PDF generado.")
        else:
            QMessageBox.information(self, "Abrir PDF", "Aún no hay un PDF generado.")

    def create_pdf(self):
        patient = self.patient_input["line"].text().strip()
        study = self.study_input["line"].text().strip()

        if not patient:
            QMessageBox.warning(self, "Falta información", "Escribe el nombre del paciente.")
            self.set_status("Falta el nombre del paciente.")
            return

        if not study:
            QMessageBox.warning(self, "Falta información", "Escribe el tipo de estudio.")
            self.set_status("Falta el tipo de estudio.")
            return

        if not self.files:
            QMessageBox.warning(self, "Sin archivos", "Agrega al menos un archivo.")
            self.set_status("No hay archivos para exportar.")
            return

        if not self.output_folder or not os.path.isdir(self.output_folder):
            QMessageBox.warning(self, "Ruta inválida", "Selecciona una carpeta de salida válida.")
            self.set_status("La carpeta de salida no es válida.")
            return

        safe_patient = sanitize_filename(patient)
        safe_study = sanitize_filename(study)
        output_name = f"{safe_patient}_{safe_study}.pdf"
        output_path = ensure_unique_path(os.path.join(self.output_folder, output_name))

        writer = PdfWriter()

        try:
            for path in self.files:
                ext = os.path.splitext(path)[1].lower()

                if ext == ".pdf":
                    reader = PdfReader(path)
                    for page in reader.pages:
                        fitted = fit_pdf_page(page, self.page_mode)
                        writer.add_page(fitted)
                else:
                    temp_pdf = image_to_pdf_bytes(
                        path,
                        page_mode=self.page_mode,
                        compression=self.compression_mode,
                    )
                    reader = PdfReader(temp_pdf)
                    for page in reader.pages:
                        writer.add_page(page)

            if len(writer.pages) == 0:
                QMessageBox.warning(self, "Sin contenido", "No se pudo generar el PDF.")
                self.set_status("No se pudo generar el PDF.")
                return

            with open(output_path, "wb") as f:
                writer.write(f)

            self.last_pdf_path = output_path
            self.update_action_buttons()
            self.set_status("PDF generado correctamente.")
            self.show_success_banner("PDF exportado correctamente")

        except Exception as e:
            self.set_status("Ocurrió un error al generar el PDF.")
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo generar el PDF.\n\nDetalle: {e}"
            )
