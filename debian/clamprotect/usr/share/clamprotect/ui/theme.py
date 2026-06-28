_FONT = '"Segoe UI", "Ubuntu", "Droid Sans", sans-serif'

DARK = f"""
* {{ font-family: {_FONT}; }}
QMainWindow, QDialog, QWidget {{
    background-color: #1e1e1e; color: #e0e0e0;
}}
QPushButton {{
    background-color: #3a3a3a; border: 1px solid #555;
    padding: 6px 16px; border-radius: 4px; color: #e0e0e0;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: #4a4a4a; }}
QPushButton:pressed {{ background-color: #2a2a2a; }}
QTableWidget {{
    background-color: #252525; alternate-background-color: #2a2a2a;
    border: 1px solid #444; gridline-color: #444;
    font-size: 13px;
}}
QHeaderView::section {{
    background-color: #333; border: 1px solid #555;
    padding: 6px; color: #e0e0e0; font-weight: bold; font-size: 13px;
}}
QTabWidget::pane {{ border: 1px solid #444; background-color: #1e1e1e; }}
QTabBar::tab {{
    background-color: #333; border: 1px solid #444;
    padding: 8px 16px; margin-right: 2px; font-size: 13px;
}}
QTabBar::tab:selected {{ background-color: #1e1e1e; border-bottom-color: #1e1e1e; }}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #252525; border: 1px solid #555;
    border-radius: 4px; padding: 4px; color: #e0e0e0; font-size: 13px;
}}
QTreeWidget {{
    background-color: #252525; alternate-background-color: #2a2a2a;
    border: 1px solid #444; font-size: 13px;
}}
QLabel {{ color: #e0e0e0; font-size: 13px; }}
QGroupBox {{
    border: 1px solid #555; border-radius: 6px;
    margin-top: 8px; padding-top: 16px; font-size: 13px;
}}
QGroupBox#statsCard {{
    border: 1px solid #555; border-radius: 6px;
    margin-top: 0; padding: 10px; background-color: #252525;
    font-size: 11px; color: #aaa;
}}
QGroupBox#statsCard QLabel[statValue="true"] {{
    font-size: 22px; font-weight: bold; color: #e0e0e0;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QComboBox {{
    background-color: #3a3a3a; border: 1px solid #555;
    border-radius: 4px; padding: 4px 8px; color: #e0e0e0; font-size: 13px;
}}
QCheckBox, QRadioButton {{ color: #e0e0e0; font-size: 13px; }}
QScrollBar:vertical {{ background-color: #2a2a2a; width: 12px; }}
QScrollBar::handle:vertical {{ background-color: #555; border-radius: 6px; min-height: 20px; }}
QProgressBar {{ background-color: #333; border: 1px solid #555; border-radius: 4px; text-align: center; color: #e0e0e0; font-size: 13px; }}
QProgressBar::chunk {{ background-color: #27ae60; border-radius: 4px; }}
"""

LIGHT = f"""
* {{ font-family: {_FONT}; }}
QMainWindow, QDialog, QWidget {{
    background-color: #f5f5f5; color: #333;
}}
QPushButton {{
    background-color: #e0e0e0; border: 1px solid #ccc;
    padding: 6px 16px; border-radius: 4px; color: #333;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: #d0d0d0; }}
QPushButton:pressed {{ background-color: #c0c0c0; }}
QTableWidget {{
    background-color: #fff; alternate-background-color: #f0f0f0;
    border: 1px solid #ddd; gridline-color: #ddd;
    font-size: 13px;
}}
QHeaderView::section {{
    background-color: #e8e8e8; border: 1px solid #ddd; padding: 6px; color: #333;
    font-weight: bold; font-size: 13px;
}}
QTabWidget::pane {{ border: 1px solid #ddd; background-color: #f5f5f5; }}
QTabBar::tab {{
    background-color: #e8e8e8; border: 1px solid #ddd;
    padding: 8px 16px; margin-right: 2px; font-size: 13px;
}}
QTabBar::tab:selected {{ background-color: #f5f5f5; border-bottom-color: #f5f5f5; }}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #fff; border: 1px solid #ccc;
    border-radius: 4px; padding: 4px; color: #333; font-size: 13px;
}}
QTreeWidget {{
    background-color: #fff; alternate-background-color: #f0f0f0;
    border: 1px solid #ddd; font-size: 13px;
}}
QLabel {{ color: #333; font-size: 13px; }}
QGroupBox {{
    border: 1px solid #ccc; border-radius: 6px;
    margin-top: 8px; padding-top: 16px; font-size: 13px;
}}
QGroupBox#statsCard {{
    border: 1px solid #ccc; border-radius: 6px;
    margin-top: 0; padding: 10px; background-color: #ffffff;
    font-size: 11px; color: #888;
}}
QGroupBox#statsCard QLabel[statValue="true"] {{
    font-size: 22px; font-weight: bold; color: #333;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QComboBox {{
    background-color: #fff; border: 1px solid #ccc;
    border-radius: 4px; padding: 4px 8px; color: #333; font-size: 13px;
}}
QCheckBox, QRadioButton {{ color: #333; font-size: 13px; }}
QScrollBar:vertical {{ background-color: #f0f0f0; width: 12px; }}
QScrollBar::handle:vertical {{ background-color: #ccc; border-radius: 6px; min-height: 20px; }}
QProgressBar {{ background-color: #e0e0e0; border: 1px solid #ccc; border-radius: 4px; text-align: center; color: #333; font-size: 13px; }}
QProgressBar::chunk {{ background-color: #27ae60; border-radius: 4px; }}
"""


def apply_theme(app, theme_name):
    if theme_name == "dark":
        app.setStyleSheet(DARK)
    elif theme_name == "light":
        app.setStyleSheet(LIGHT)
    else:
        import platform
        if platform.system() == "Linux":
            try:
                import subprocess
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                    capture_output=True, text=True, timeout=5,
                )
                is_dark = "dark" in result.stdout.lower()
            except Exception:
                is_dark = False
            app.setStyleSheet(DARK if is_dark else LIGHT)
        else:
            app.setStyleSheet(LIGHT)
