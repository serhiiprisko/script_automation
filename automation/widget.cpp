#include "widget.h"
#include "ui_widget.h"
#include <QSettings>
#include <QMessageBox>

Widget::Widget(QWidget *parent)
    : QWidget(parent)
    , ui(new Ui::Widget)
{
    m_process.setWorkingDirectory(QCoreApplication::applicationDirPath());
    m_process.setReadChannel(QProcess::StandardOutput);

    ui->setupUi(this);

    loadSettings();

    m_isWorking = false;
    ui->pushButton_stop->setEnabled(false);

    m_timer.setInterval(1000);
    connect(&m_timer, SIGNAL(timeout()), this, SLOT(on_timer_timeout()));
}

Widget::~Widget()
{
    delete ui;
}

void Widget::saveSettings()
{
    QSettings settings(QCoreApplication::applicationDirPath() + "/settings.ini", QSettings::IniFormat);
    settings.setIniCodec("UTF-8");

    settings.setValue("isShopware", m_isShopware);
    settings.setValue("currentTab", ui->tabWidget->currentIndex());
    settings.setValue("isRound00", m_isRound00);

    settings.setValue("keyword", ui->lineEdit_keyword->text().toUtf8().data());

    QString singleUrl = ui->lineEdit_singleUrl->text();
    singleUrl.replace("%", "%%");
    settings.setValue("singleUrl", singleUrl);
    settings.setValue("max_products", ui->lineEdit_max_products->text());
    settings.setValue("max_images", ui->lineEdit_max_images->text());
    settings.setValue("min_price_reduction", ui->lineEdit_min_price_reduction->text());
    settings.setValue("max_price_reduction", ui->lineEdit_max_price_reduction->text());
    settings.setValue("min_price_filter", ui->lineEdit_min_price_filter->text());
    settings.setValue("max_price_filter", ui->lineEdit_max_price_filter->text());
    settings.setValue("captcha_api_key", ui->lineEdit_captcha_api_key->text());
    settings.setValue("otto", ui->checkBox_otto->isChecked());
    settings.setValue("mediamarkt", ui->checkBox_mediamarkt->isChecked());
    settings.setValue("fahrrad", ui->checkBox_fahrrad->isChecked());
    settings.setValue("title_search", ui->checkBox_title->isChecked());

    settings.setValue("shopware_admin", ui->lineEdit_shopwareAdmin->text());
    settings.setValue("shopware_api_key", ui->lineEdit_shopwareApiKey->text());
    settings.setValue("shopware_url", ui->lineEdit_shopwareURL->text());

    settings.setValue("presta_api_key", ui->lineEdit_prestaApiKey->text());
    settings.setValue("presta_url", ui->lineEdit_prestaURL->text());

    QString url = ui->plainTextEdit_url->toPlainText();
    url.replace("%", "%%");
    settings.setValue("url", url.toUtf8().data());
}

void Widget::loadSettings()
{
    QSettings settings(QCoreApplication::applicationDirPath() + "/settings.ini", QSettings::IniFormat);
    settings.setIniCodec("UTF-8");

    m_isShopware = settings.value("isShopware", true).toBool();
    if (m_isShopware)
        on_option_shopware_clicked();
    else on_option_prestashop_clicked();

    m_isRound00 = settings.value("isRound00", true).toBool();
    if (m_isRound00)
        ui->option_00->setChecked(true);
    else ui->option_99->setChecked(true);

    ui->tabWidget->setCurrentIndex(settings.value("currentTab", 0).toInt());

    QString singleUrl = QString::fromUtf8(settings.value("singleUrl").toByteArray());
    singleUrl.replace("%%", "%");
    ui->lineEdit_singleUrl->setText(singleUrl);
    ui->lineEdit_keyword->setText(QString::fromUtf8(settings.value("keyword").toByteArray()));
    ui->lineEdit_max_products->setText(settings.value("max_products").toString());
    ui->lineEdit_max_images->setText(settings.value("max_images").toString());
    ui->lineEdit_min_price_reduction->setText(settings.value("min_price_reduction").toString());
    ui->lineEdit_max_price_reduction->setText(settings.value("max_price_reduction").toString());
    ui->lineEdit_min_price_filter->setText(settings.value("min_price_filter").toString());
    ui->lineEdit_max_price_filter->setText(settings.value("max_price_filter").toString());
    ui->lineEdit_captcha_api_key->setText(settings.value("captcha_api_key").toString());
    ui->checkBox_otto->setChecked(settings.value("otto", false).toBool());
    ui->checkBox_mediamarkt->setChecked(settings.value("mediamarkt", false).toBool());
    ui->checkBox_fahrrad->setChecked(settings.value("fahrrad", false).toBool());
    ui->checkBox_title->setChecked(settings.value("title_search", false).toBool());

    ui->lineEdit_shopwareAdmin->setText(settings.value("shopware_admin").toString());
    ui->lineEdit_shopwareApiKey->setText(settings.value("shopware_api_key").toString());
    ui->lineEdit_shopwareURL->setText(settings.value("shopware_url").toString());

    ui->lineEdit_prestaApiKey->setText(settings.value("presta_api_key").toString());
    ui->lineEdit_prestaURL->setText(settings.value("presta_url").toString());

    QString url = QString::fromUtf8(settings.value("url").toByteArray());
    url.replace("%%", "%");
    ui->plainTextEdit_url->setPlainText(url);
}

void Widget::closeEvent(QCloseEvent *event)
{
    if (m_isWorking)
        on_pushButton_stop_clicked();
    saveSettings();
}

void Widget::on_option_shopware_clicked()
{
    m_isShopware = true;
    ui->option_shopware->setChecked(true);
    ui->widget_shopware->setVisible(true);
    ui->widget_prestashop->setVisible(false);
}

void Widget::on_option_prestashop_clicked()
{
    m_isShopware = false;
    ui->option_prestashop->setChecked(true);
    ui->widget_shopware->setVisible(false);
    ui->widget_prestashop->setVisible(true);
}

void Widget::on_option_00_clicked()
{
    m_isRound00 = true;
}

void Widget::on_option_99_clicked()
{
    m_isRound00 = false;
}

void Widget::on_pushButton_start_clicked()
{
    saveSettings();

    m_process.start("python py/1.py");
    if (m_process.state() != QProcess::NotRunning) {
        ui->pushButton_start->setEnabled(false);
        ui->pushButton_stop->setEnabled(true);
        ui->groupBox_shop->setEnabled(false);
        ui->groupBox_settings->setEnabled(false);
        ui->tabWidget->setEnabled(false);

        m_isWorking = true;
        m_timer.start();
    }
}

void Widget::on_pushButton_stop_clicked()
{
    m_timer.stop();
    m_process.kill();
    m_process.waitForFinished();

    ui->pushButton_start->setEnabled(true);
    ui->pushButton_stop->setEnabled(false);
    ui->groupBox_shop->setEnabled(true);
    ui->groupBox_settings->setEnabled(true);
    ui->tabWidget->setEnabled(true);
    m_isWorking = false;
}

void Widget::on_pushButton_clearLog_clicked()
{
    ui->plainTextEdit_log->setPlainText("");
}

void Widget::on_timer_timeout()
{
    QString str = QString::fromLocal8Bit(m_process.readAllStandardOutput());
    if (str.isEmpty() == false) {
        ui->plainTextEdit_log->setPlainText(ui->plainTextEdit_log->toPlainText() + str);
        ui->plainTextEdit_log->moveCursor(QTextCursor::End, QTextCursor::MoveAnchor);
    }
    if (m_process.processId() == 0) {
        QMessageBox::information(this, "", "python process stopped running.");
        on_pushButton_stop_clicked();
        return;
    }
}
