# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'style_editorTbshkq.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDockWidget, QLineEdit, QMainWindow,
    QMenuBar, QScrollArea, QSizePolicy, QStatusBar,
    QToolBar, QVBoxLayout, QWidget)

from editor_tab_widget import EditorTabWidget
from sizing_dock_content import SizingDockContent

class Ui_EditorWindow(object):
    def setupUi(self, EditorWindow):
        if not EditorWindow.objectName():
            EditorWindow.setObjectName(u"EditorWindow")
        EditorWindow.resize(800, 600)
        EditorWindow.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        self.centralwidget = QWidget(EditorWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_2 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.tabWidget_editor = EditorTabWidget(self.centralwidget)
        self.tabWidget_editor.setObjectName(u"tabWidget_editor")
        self.tabWidget_editor.setTabsClosable(True)
        self.tabWidget_editor.setMovable(True)
        self.tabWidget_editor.setTabBarAutoHide(True)
        self.tab_welcome = QWidget()
        self.tab_welcome.setObjectName(u"tab_welcome")
        self.tabWidget_editor.addTab(self.tab_welcome, "")

        self.verticalLayout_2.addWidget(self.tabWidget_editor)

        EditorWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(EditorWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 800, 33))
        EditorWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(EditorWindow)
        self.statusbar.setObjectName(u"statusbar")
        EditorWindow.setStatusBar(self.statusbar)
        self.dockWidget_components = QDockWidget(EditorWindow)
        self.dockWidget_components.setObjectName(u"dockWidget_components")
        self.dockWidgetContents_comp = SizingDockContent()
        self.dockWidgetContents_comp.setObjectName(u"dockWidgetContents_comp")
        self.verticalLayout = QVBoxLayout(self.dockWidgetContents_comp)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.lineEdit_component = QLineEdit(self.dockWidgetContents_comp)
        self.lineEdit_component.setObjectName(u"lineEdit_component")

        self.verticalLayout.addWidget(self.lineEdit_component)

        self.scrollArea_components = QScrollArea(self.dockWidgetContents_comp)
        self.scrollArea_components.setObjectName(u"scrollArea_components")
        self.scrollArea_components.setWidgetResizable(True)
        self.scrollAreaCompContents = QWidget()
        self.scrollAreaCompContents.setObjectName(u"scrollAreaCompContents")
        self.scrollAreaCompContents.setGeometry(QRect(0, 0, 130, 466))
        self.scrollArea_components.setWidget(self.scrollAreaCompContents)

        self.verticalLayout.addWidget(self.scrollArea_components)

        self.dockWidget_components.setWidget(self.dockWidgetContents_comp)
        EditorWindow.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dockWidget_components)
        self.dockWidget_details = QDockWidget(EditorWindow)
        self.dockWidget_details.setObjectName(u"dockWidget_details")
        self.dockWidgetContents_details = SizingDockContent()
        self.dockWidgetContents_details.setObjectName(u"dockWidgetContents_details")
        self.dockWidget_details.setWidget(self.dockWidgetContents_details)
        EditorWindow.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockWidget_details)
        self.toolBar = QToolBar(EditorWindow)
        self.toolBar.setObjectName(u"toolBar")
        EditorWindow.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolBar)

        self.retranslateUi(EditorWindow)

        self.tabWidget_editor.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(EditorWindow)
    # setupUi

    def retranslateUi(self, EditorWindow):
        EditorWindow.setWindowTitle(QCoreApplication.translate("EditorWindow", u"MainWindow", None))
        self.tabWidget_editor.setTabText(self.tabWidget_editor.indexOf(self.tab_welcome), QCoreApplication.translate("EditorWindow", u"Welcome", None))
        self.dockWidget_components.setWindowTitle(QCoreApplication.translate("EditorWindow", u"Components", None))
        self.dockWidget_details.setWindowTitle(QCoreApplication.translate("EditorWindow", u"Details", None))
        self.toolBar.setWindowTitle(QCoreApplication.translate("EditorWindow", u"toolBar", None))
    # retranslateUi

