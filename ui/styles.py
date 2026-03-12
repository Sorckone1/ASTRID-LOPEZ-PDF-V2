APP_STYLES = """
QWidget {
    background: transparent;
    color: #4D3C45;
    font-family: "Montserrat", "Helvetica Neue", "Arial";
}

#RootWindow {
    background-color: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #F9E2EB,
        stop: 0.45 #F4D2E4,
        stop: 1 #EFC6DD
    );
}

#MainCard {
    background: rgba(255, 252, 253, 0.62);
    border: 1px solid rgba(255, 255, 255, 0.78);
    border-radius: 30px;
}

#TitleLabel {
    color: #7A4D63;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
}

#HeroLabel {
    color: #684252;
    font-size: 28px;
    font-weight: 700;
}

#SectionLabel {
    color: #936177;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}

QLineEdit {
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(255, 255, 255, 0.96);
    border-radius: 16px;
    padding: 8px 12px;
    font-size: 13px;
    color: #5E4753;
    selection-background-color: rgba(241, 83, 161, 0.22);
}

QLineEdit:focus {
    background: rgba(255, 255, 255, 0.98);
    border: 1px solid rgba(234, 118, 177, 0.85);
}

#UploadCard {
    background: rgba(255, 255, 255, 0.30);
    border: 1px solid rgba(255, 255, 255, 0.74);
    border-radius: 24px;
}

#UploadBadge {
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(255, 255, 255, 1);
    border-radius: 29px;
    color: #E954A1;
    font-size: 34px;
    font-weight: 500;
}

#UploadTitle {
    color: #8E5870;
    font-size: 18px;
    font-weight: 700;
}

#UploadSubtext {
    color: rgba(95, 69, 83, 0.88);
    font-size: 12px;
    font-weight: 500;
}

#UploadCount {
    color: rgba(116, 84, 97, 0.72);
    font-size: 11px;
    font-weight: 500;
}

#MiniToolbar {
    background: rgba(255, 255, 255, 0.24);
    border: 1px solid rgba(255, 255, 255, 0.50);
    border-radius: 20px;
}

#BottomBar {
    background: rgba(255, 255, 255, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.90);
    border-radius: 20px;
}

#SmallMuted {
    color: rgba(90, 65, 77, 0.82);
    font-size: 12px;
    font-weight: 500;
}

#SoftButton {
    background: rgba(255, 255, 255, 0.86);
    border: 1px solid rgba(255, 255, 255, 0.96);
    border-radius: 17px;
    padding: 10px 16px;
    color: #83586D;
    font-size: 13px;
    font-weight: 600;
}

#SoftButton:hover {
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid rgba(255, 255, 255, 1);
}

#SoftButton:pressed {
    background: rgba(248, 242, 245, 0.96);
}

#SoftButton:disabled {
    background: rgba(255, 255, 255, 0.46);
    color: rgba(131, 88, 109, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.52);
}

#PrimaryButton {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #FF7ABF,
        stop: 1 #EC4F9E
    );
    border: 1px solid rgba(255, 255, 255, 0.66);
    border-radius: 20px;
    padding: 12px 24px;
    color: white;
    font-size: 15px;
    font-weight: 700;
}

#PrimaryButton:hover {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #FF86C5,
        stop: 1 #F05AA6
    );
}

#PrimaryButton:pressed {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #F06DB2,
        stop: 1 #DA468F
    );
}

#PrimaryButton:disabled {
    background: rgba(230, 170, 200, 0.70);
    color: rgba(255,255,255,0.72);
    border: 1px solid rgba(255,255,255,0.45);
}
"""
