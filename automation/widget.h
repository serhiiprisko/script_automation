#ifndef WIDGET_H
#define WIDGET_H

#include <QWidget>
#include <QProcess>
#include <QTimer>

QT_BEGIN_NAMESPACE
namespace Ui { class Widget; }
QT_END_NAMESPACE

class Widget : public QWidget
{
    Q_OBJECT

public:
    Widget(QWidget *parent = nullptr);
    ~Widget();
protected:
    void closeEvent(QCloseEvent *event);
public slots:
    void on_option_shopware_clicked();
    void on_option_prestashop_clicked();

    void on_option_00_clicked();
    void on_option_99_clicked();

    void on_pushButton_start_clicked();
    void on_pushButton_stop_clicked();
    void on_pushButton_clearLog_clicked();

    void on_timer_timeout();
private:
    Ui::Widget *ui;

    bool m_isShopware;
    bool m_isRound00;
    bool m_isWorking;

    void saveSettings();
    void loadSettings();

    QProcess m_process;
    QTimer m_timer;
};
#endif // WIDGET_H
