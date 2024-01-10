#include "widget.h"

#include <QApplication>
#include <QFile>

int main(int argc, char *argv[])
{
    QApplication a(argc, argv);

    QFile file(":/dark.qss");
    file.open(QIODevice::ReadOnly | QIODevice::Text);
    QString style = file.readAll();
    a.setStyleSheet(style);
    file.close();

    Widget w;
    w.show();
    return a.exec();
}
