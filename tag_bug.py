import sys
import os
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QFileDialog, QMessageBox, QVBoxLayout, QWidget, QLabel, QPushButton, QGridLayout, QHBoxLayout, QMenu, QInputDialog, QProgressBar, QRubberBand, QShortcut, QDialog, QLineEdit
from PyQt5.QtGui import QPixmap, QContextMenuEvent, QImage, QKeySequence, QIcon, QPainter, QPen
from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from create_db import LadybirdDB, Base 

class ImageLabel(QLabel):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setStyleSheet("QLabel { border: 2px solid transparent; }")
        self.selected = False

    def setSelected(self, selected):
        self.selected = selected
        self.setStyleSheet("QLabel { border: 2px solid %s; }" % ("red" if self.selected else "transparent"))

    def contextMenuEvent(self, event: QContextMenuEvent):
        context_menu = QMenu(self)
        
        # Detail 메뉴 추가
        detail_action = context_menu.addAction("Detail")
        
        remove_menu = context_menu.addMenu("Remove")
        remove_from_path_action = remove_menu.addAction("Remove from Path")
        remove_from_db_action = remove_menu.addAction("Remove from DB")
        tag_menu = context_menu.addMenu("Tag")
        
        for cls in self.parent().parent().all_classes:
            tag_action = tag_menu.addAction(cls)
            tag_action.triggered.connect(lambda checked, cls=cls: self.parent().parent().update_image_class(cls))
        
        tag_menu.addSeparator()
        
        add_tag_action = tag_menu.addAction("Add Tag")
        add_tag_action.triggered.connect(self.parent().parent().add_new_tag)
        
        action = context_menu.exec_(self.mapToGlobal(event.pos()))

        if action == remove_from_path_action:
            self.parent().parent().remove_from_path()
        elif action == remove_from_db_action:
            self.parent().parent().remove_selected_images()
        elif action == detail_action:
            ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(self.image_path)))
            self.parent().parent().show_detail_for_image(ladybird_id)

class DetailWindow(QMainWindow):
    def __init__(self, parent=None, db_session=None):
        super().__init__(parent)
        self.parent = parent
        self.db_session = db_session
        self.selected_ladybirds = set()
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('Image Detail')
        self.setGeometry(200, 200, 1200, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 상단 텍스트 정보
        self.info_text = QLabel("Not Selected.")
        self.info_text.setAlignment(Qt.AlignCenter)
        self.info_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        main_layout.addWidget(self.info_text)
        main_layout.addSpacing(10)
        
        # 이미지를 위한 하단 레이아웃
        image_layout = QHBoxLayout()
        
        # 왼쪽 이미지
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.ladybird_label = QLabel()
        self.ladybird_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(QLabel("Ladybird Image"))
        left_layout.addWidget(self.ladybird_label)
        image_layout.addWidget(left_panel)
        
        # 오른쪽 이미지
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.pattern_label = QLabel()
        self.pattern_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(QLabel("Pattern Image"))
        right_layout.addWidget(self.pattern_label)
        image_layout.addWidget(right_panel)
        
        main_layout.addLayout(image_layout)
        
    def update_detail(self, ladybird_id=None):
        if not ladybird_id:
            self.info_text.setText("Not Selected.")
            self.ladybird_label.clear()
            self.pattern_label.clear()
            return
            
        base_path = f'/data1/lpf/augmented_230823/{ladybird_id}'
        ladybird_path = f'{base_path}/ladybirds'
        pattern_path = f'{base_path}/patterns'
        
        # 정보 텍스트 업데이트
        info = f"Ladybird ID: {ladybird_id}\n"
        info += f"Saved Path: {base_path}\n"
        info += f"Tag: {self.db_session.query(LadybirdDB.class_).filter_by(id=ladybird_id).first()[0]}\n"
        if ladybird_id in self.selected_ladybirds:
            info += "Status: Selected (Saved in Special Path)"
        self.info_text.setText(info)
        
        # 이미지 업데이트
        if os.path.exists(ladybird_path):
            ladybird_image = os.listdir(ladybird_path)[0]
            pixmap = QPixmap(os.path.join(ladybird_path, ladybird_image))
            self.ladybird_label.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))
            
        if os.path.exists(pattern_path):
            pattern_image = os.listdir(pattern_path)[0]
            pixmap = QPixmap(os.path.join(pattern_path, pattern_image))
            painter = QPainter(pixmap)
            painter.setPen(QPen(Qt.green, 2))
            painter.drawRect(36, 12,  55, 105)
            painter.end()

            self.pattern_label.setPixmap(pixmap.scaled(400, 400, Qt.KeepAspectRatio))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.detail_window = None
        self.detail_windows = []  # 디테일 윈도우 참조 저장
        self.initUI()
        self.db_session = None
        self.grid_width = 10
        self.grid_height = 10
        self.images_per_page = self.grid_width * self.grid_height
        self.current_page = 0
        self.selected_images = set()
        self.class_filters = set()
        self.all_classes = set()
        self.rubberBand = None
        self.origin = QPoint()
        self.npy_paths = None

    def initUI(self):
        self.setWindowTitle('Tag Bug')
        self.setGeometry(100, 100, 800, 600)

        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        self.view_menu = menubar.addMenu('View')

        load_db_action = QAction('Load DB', self)
        load_db_action.triggered.connect(self.load_db)
        file_menu.addAction(load_db_action)

        file_menu.addSeparator()

        load_npy_action = QAction('Load NPY', self)
        load_npy_action.triggered.connect(self.load_npy)
        file_menu.addAction(load_npy_action)

        self.view_action_list = ['NPY Deactivate', 'All Activate', 'All Deactivate']
      
        npy_deactivate_action = QAction('NPY Deactivate', self)
        npy_deactivate_action.triggered.connect(self.npy_deactivate)
        self.view_menu.addAction(npy_deactivate_action)
        self.view_menu.addSeparator()

        all_activate_action = QAction('All Activate', self)
        all_activate_action.triggered.connect(self.all_activate)
        self.view_menu.addAction(all_activate_action)

        all_deactivate_action = QAction('All Deactivate', self)
        all_deactivate_action.triggered.connect(self.all_deactivate)
        self.view_menu.addAction(all_deactivate_action)


        select_menu = menubar.addMenu('Select')
        unselect_all_action = QAction('Unselect All', self)
        unselect_all_action.triggered.connect(self.unselect_all)
        select_menu.addAction(unselect_all_action)
        
        option_menu = menubar.addMenu('Option')

        grayscale_action = QAction('Grayscale', self, checkable=True)
        self.grayscale = False
        grayscale_action.setChecked(False)
        grayscale_action.triggered.connect(self.toggle_grayscale)
        option_menu.addAction(grayscale_action)

        ratio_action = QAction("Grid Ratio", self)
        ratio_action.triggered.connect(self.show_ratio_dialog)
        option_menu.addAction(ratio_action)
        
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        self.image_paths_label = QLabel(self)
        self.layout.addWidget(self.image_paths_label)

        self.grid_layout = QGridLayout()
        self.layout.addLayout(self.grid_layout)

        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)

        self.page_info_label = QLabel(self)
        self.button_layout.addWidget(self.page_info_label)
        
        self.prev_button = QPushButton('Prev Page', self)
        self.prev_button.clicked.connect(self.prev_page)
        self.button_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton('Next Page', self)
        self.next_button.clicked.connect(self.next_page)
        self.button_layout.addWidget(self.next_button)

        self.progress_bar = QProgressBar(self)
        self.layout.addWidget(self.progress_bar)
        self.progress_bar.hide()
        self.select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        self.select_all_shortcut.activated.connect(self.select_all_images)

    def select_all_images(self):
        for i in range(self.grid_layout.rowCount()):
            for j in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(i, j)
                if item:
                    widget = item.widget()
                    if isinstance(widget, ImageLabel):
                        widget.setSelected(True)
                        self.toggle_image_selection(True, widget.image_path)
        self.display_images()
        
    def load_db(self):
        options = QFileDialog.Options()
        initial_dir = '/data1/lpf/database/'
        db_path, _ = QFileDialog.getOpenFileName(self, "Select DB File", initial_dir, "SQLite Files (*.db);;All Files (*)", options=options)
        if db_path:
            try:
                engine = create_engine(f'sqlite:///{db_path}')
                Base.metadata.bind = engine
                DBSession = sessionmaker(bind=engine)
                self.db_session = DBSession()
                self.load_all_classes()
                self.load_class_filters()
                self.display_images()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred while loading the database: {str(e)}")

    def load_npy(self):
        options = QFileDialog.Options()
        npy_path, _ = QFileDialog.getOpenFileName(self, "Select NPY File", "", "Numpy Files (*.npy)", options=options)
        if npy_path:
            try:
                npy_paths = np.load(npy_path, allow_pickle=True)
                self.npy_paths = [path.split('/')[4] for path in npy_paths]
                self.display_images()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred while loading the NPY file: {str(e)}")

    def load_all_classes(self):
        if self.db_session:
            try:
                classes = self.db_session.query(LadybirdDB.class_).distinct().all()
                new_classes = {cls[0] if cls[0] else 'None' for cls in classes}
                self.update_new_classes(new_classes)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred while loading all classes: {str(e)}")

    def update_new_classes(self, new_classes):
        added_classes = new_classes - self.all_classes
        if added_classes:
            self.all_classes.update(added_classes)
            self.class_filters.update(added_classes)
            self.update_class_filter_menu_for_new_classes(added_classes)

    def update_class_filter_menu_for_new_classes(self, new_classes):
        for cls in new_classes:
            action = QAction(cls, self, checkable=True)
            action.setChecked(True)
            action.triggered.connect(self.update_class_filter)
            self.view_menu.addAction(action)

    def load_class_filters(self):
        self.class_filters = self.all_classes.copy()
        self.update_class_filter_menu()

    def update_class_filter_menu(self):
        for action in self.view_menu.actions():
            if action.text() not in ['NPY Deactivate', 'All Activate', 'All Deactivate']:
                self.view_menu.removeAction(action)
        self.view_menu.addSeparator()
        for cls in self.all_classes:
            action = QAction(cls, self, checkable=True)
            action.setChecked(cls in self.class_filters)
            action.triggered.connect(self.update_class_filter)
            self.view_menu.addAction(action)

    def update_class_filter(self):
        action = self.sender()
        if action.isChecked():
            self.class_filters.add(action.text())
        else:
            self.class_filters.discard(action.text())
        self.display_images()

    def all_activate(self):
        self.class_filters = self.all_classes.copy()
        for action in self.view_menu.actions():
            if action.text() not in ['NPY Deactivate', 'All Activate', 'All Deactivate']:
                action.setChecked(True)
        self.display_images()

    def all_deactivate(self):
        self.class_filters.clear()
        for action in self.view_menu.actions():
            if action.text() not in ['NPY Deactivate', 'All Activate', 'All Deactivate']:
                action.setChecked(False)
        self.display_images()

    def display_images(self):
        for i in reversed(range(self.grid_layout.count())): 
            widget_to_remove = self.grid_layout.itemAt(i).widget()
            self.grid_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)
        self.load_all_classes()
        if self.db_session:
            query = self.db_session.query(LadybirdDB).filter(LadybirdDB.class_.in_(self.class_filters))
            if self.npy_paths is not None:
                query = query.filter(LadybirdDB.id.in_(self.npy_paths))
            total_count = query.count()
            start_index = self.current_page * self.images_per_page
            ladybirds = query.offset(start_index).limit(self.images_per_page).all()
            
            self.page_info_label.setText(f"Page: {start_index + 1} - {start_index + len(ladybirds)} / Total Images: {total_count}")
            
            position = [(i, j) for i in range(self.grid_height) for j in range(self.grid_width)]
            
            for pos, ladybird in zip(position, ladybirds):
                base_path = f'/data1/lpf/augmented_230823/{ladybird.id}/ladybirds/'
                if os.path.exists(base_path):
                    for filename in os.listdir(base_path)[:1]:
                        image_path = os.path.join(base_path, filename)
                        label = ImageLabel(image_path, self)
                        pixmap = self.load_image(image_path)
                        if pixmap:
                            pixmap = pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            label.setPixmap(pixmap)
                            if image_path in self.selected_images:
                                label.setSelected(True)
                            self.grid_layout.addWidget(label, *pos)
                        else:
                            error_label = QLabel(f"Failed to load image: {image_path}", self)
                            self.grid_layout.addWidget(error_label, *pos)

    def load_image(self, image_path):
        if os.path.exists(image_path):
            image = QImage(image_path)
            if not image.isNull():
                if self.grayscale:
                    image = image.convertToFormat(QImage.Format_Grayscale8)
                return QPixmap.fromImage(image)
            else:
                return QPixmap.fromImage(image)
        print(f"Cannot load image: {image_path}")
        return None

    def next_page(self):
        query = self.db_session.query(LadybirdDB).filter(LadybirdDB.class_.in_(self.class_filters))
        if self.npy_paths is not None:
            query = query.filter(LadybirdDB.id.in_(self.npy_paths))
        total_count = query.count()
        if (self.current_page + 1) * self.images_per_page < total_count:
            self.current_page += 1
            self.display_images()
    
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.display_images()

    def npy_deactivate(self):
        self.npy_paths = None
        self.display_images()

    def remove_selected_images(self):
        if not self.selected_images:
            QMessageBox.warning(self, "Warning", "No images selected.")
            return
        
        reply = QMessageBox.question(self, 'Confirm', f'{len(self.selected_images)} images will be deleted from DB.',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            for image_path in self.selected_images:
                ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
                ladybird = self.db_session.query(LadybirdDB).filter_by(id=ladybird_id).first()
                if ladybird:
                    self.db_session.delete(ladybird)
            
            self.db_session.commit()
            
            self.selected_images.clear()
            self.display_images()
            QMessageBox.information(self, "Success", "Selected images removed from DB.")

    def remove_from_path(self):
        if not self.selected_images:
            QMessageBox.warning(self, "Warning", "No images selected.")
            return
        
        reply = QMessageBox.question(self, 'Confirm', f'{len(self.selected_images)} images will be removed from path.',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            for image_path in self.selected_images:
                ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
                if self.npy_paths is not None and ladybird_id in self.npy_paths:
                    self.npy_paths.remove(ladybird_id)
            self.selected_images.clear()
            self.display_images()
            QMessageBox.information(self, "Success", "Selected images removed from path.")

    def toggle_image_selection(self, selected, image_path):
        if selected:
            self.selected_images.add(image_path)
        else:
            self.selected_images.discard(image_path)

    def update_image_class(self, new_class):
        if not self.selected_images:
            QMessageBox.warning(self, "Warning", "No images selected.")
            return
        
        for image_path in self.selected_images:
            ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
            ladybird = self.db_session.query(LadybirdDB).filter_by(id=ladybird_id).first()
            if ladybird:
                ladybird.class_ = new_class
            else:
                QMessageBox.critical(self, "Error", f"Image {image_path} not found in the database.")
                return
            
        if self.selected_images:
            image_path = list(self.selected_images)[0]
            ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
            if hasattr(self, 'detail_window') and self.detail_window is not None:
                self.detail_window.update_detail(ladybird_id)
                        
        self.db_session.commit()
        self.selected_images.clear()
        self.load_all_classes()
        self.display_images()

    def toggle_grayscale(self):
        self.grayscale = not self.grayscale
        self.display_images()
    def unselect_all(self):
        self.selected_images.clear()
        self.display_images()

    def add_new_tag(self):
        new_class, ok = QInputDialog.getText(self, "Add New Tag", "Enter new class:")
        if ok and new_class and new_class not in self.all_classes:
            self.update_new_classes({new_class})
            self.update_image_class(new_class)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            if not self.rubberBand:
                self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if self.rubberBand:
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if self.rubberBand:
            self.rubberBand.hide()
            selected_rect = self.rubberBand.geometry()
            self.select_images_in_rect(selected_rect, event.modifiers() & Qt.ShiftModifier)

    def select_images_in_rect(self, rect, add_to_selection):
        for i in range(self.grid_layout.rowCount()):
            for j in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(i, j)
                if item:
                    widget = item.widget()
                    if isinstance(widget, ImageLabel):
                        if rect.intersects(widget.geometry()):
                            if add_to_selection:
                                widget.selected = True
                                widget.setStyleSheet("QLabel { border: 2px solid red; }")
                                self.toggle_image_selection(True, widget.image_path)
                            else:
                                widget.selected = not widget.selected
                                widget.setStyleSheet("QLabel { border: 2px solid %s; }" % ("red" if widget.selected else "transparent"))
                                self.toggle_image_selection(widget.selected, widget.image_path)

    def show_detail(self):
        if not self.detail_window:
            self.detail_window = DetailWindow(self, self.db_session)
        self.detail_window.show()
        
        # 현재 선택된 이미지가 있다면 업데이트
        if self.selected_images:
            image_path = list(self.selected_images)[0]
            ladybird_id = os.path.basename(os.path.dirname(os.path.dirname(image_path)))
            self.detail_window.update_detail(ladybird_id)

    def show_detail_for_image(self, ladybird_id):
        if not self.detail_window:
            self.detail_window = DetailWindow(self, self.db_session)
        self.detail_window.show()
        self.detail_window.update_detail(ladybird_id)


    def show_ratio_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Set Grid Ratio")
        layout = QVBoxLayout()
        
        width_layout = QHBoxLayout()
        width_label = QLabel("Width:")
        self.width_input = QLineEdit()
        self.width_input.setText(str(self.grid_width))
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_input)
        
        height_layout = QHBoxLayout()
        height_label = QLabel("Height:")
        self.height_input = QLineEdit()
        self.height_input.setText(str(self.grid_height))
        height_layout.addWidget(height_label)
        height_layout.addWidget(self.height_input)
        
        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(lambda: self.apply_ratio(dialog))
        
        layout.addLayout(width_layout)
        layout.addLayout(height_layout)
        layout.addWidget(apply_button)
        dialog.setLayout(layout)
        dialog.exec_()

    def apply_ratio(self, dialog):
        try:
            new_width = int(self.width_input.text())
            new_height = int(self.height_input.text())
            if new_width > 0 and new_height > 0:
                self.grid_width = new_width
                self.grid_height = new_height
                self.images_per_page = self.grid_width * self.grid_height
                
                # 이미지 크기(100) + 여백(20)을 고려한 새로운 창 크기 계산
                new_window_width = (self.grid_width * 100)  # 좌우 여백 40px 추가
                new_window_height = (self.grid_height * 126)  # 상단 메뉴바, 버튼 등 고려하여 120px 추가
                
                # 창 크기 조정
                self.resize(new_window_width, new_window_height)
                
                dialog.accept()
                self.display_images()
        except ValueError:
            QMessageBox.warning(self, "Error", "Please enter valid numbers")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    app.setWindowIcon(QIcon('./icon.png')) 
    main_window.show()
    sys.exit(app.exec_())
