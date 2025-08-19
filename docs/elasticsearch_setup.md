
# Установка и настройка Elasticsearch на Ubuntu 24.04

Этот документ представляет собой пошаговое руководство по установке и базовой настройке Elasticsearch и Kibana на сервере под управлением Ubuntu 24.04 LTS.

## Шаг 1: Установка Java

Elasticsearch построен на Java, поэтому первым делом необходимо установить Java Development Kit (JDK). Elasticsearch включает в себя собственную версию OpenJDK, но установка системной Java является хорошей практикой. [1]

```bash
# Обновляем список пакетов
sudo apt update

# Устанавливаем OpenJDK 17 (долгосрочная поддержка)
sudo apt install -y openjdk-17-jdk

# Проверяем успешность установки
java -version
```

## Шаг 2: Установка Elasticsearch

Elasticsearch не входит в стандартные репозитории Ubuntu, поэтому его необходимо добавить вручную. [2]

### 2.1. Импорт GPG-ключа Elasticsearch

Этот ключ используется для проверки подлинности пакетов Elasticsearch. [3]

```bash
# Устанавливаем необходимые пакеты
sudo apt install -y apt-transport-https curl gpg

# Скачиваем и устанавливаем публичный ключ подписи Elastic
curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg
```

### 2.2. Добавление репозитория Elasticsearch

Теперь добавим репозиторий в список источников APT. [5]

```bash
echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
```

### 2.3. Установка пакета

Обновим список пакетов еще раз и установим Elasticsearch.

```bash
sudo apt update
sudo apt install -y elasticsearch
```

## Шаг 3: Базовая настройка Elasticsearch

Основной конфигурационный файл находится в `/etc/elasticsearch/elasticsearch.yml`. Для локальной разработки рекомендуется настроить Elasticsearch для работы только на локальном хосте. [5]

### 3.1. Основной конфигурационный файл

Откройте файл для редактирования:

```bash
sudo nano /etc/elasticsearch/elasticsearch.yml
```

Найдите строку `network.host` и раскомментируйте ее, установив значение `localhost` или `127.0.0.1`. Это важно для безопасности, чтобы предотвратить несанкционированный доступ извне. [5]

```yaml
# ================================ Network =================================
#
# By default Elasticsearch is only accessible on localhost. Set a different
# address here to expose this node on the network:
#
network.host: 127.0.0.1
#
# ==========================================================================
```

Сохраните и закройте файл (в `nano` это `CTRLX`, затем `Y` и `Enter`).

## Шаг 4: Запуск и проверка Elasticsearch

### 4.1. Запуск сервиса

После изменения конфигурации необходимо перезагрузить `systemd` и запустить сервис Elasticsearch. [5]

```bash
# Перезагружаем конфигурацию systemd
sudo systemctl daemon-reload

# Запускаем сервис Elasticsearch
sudo systemctl start elasticsearch.service

# Включаем автозапуск сервиса при старте системы
sudo systemctl enable elasticsearch.service
```

### 4.2. Проверка статуса

Убедитесь, что сервис запущен и работает без ошибок:

```bash
sudo systemctl status elasticsearch.service
```

Теперь выполните `curl` запрос, чтобы проверить, что узел Elasticsearch отвечает:

```bash
curl -X GET "http://localhost:9200"
```

Вы должны получить JSON-ответ с информацией о кластере, например:

```json
{
  "name" : "your-hostname",
  "cluster_name" : "elasticsearch",
  "cluster_uuid" : "...",
  "version" : { ... },
  "tagline" : "You Know, for Search"
}
```

## Шаг 5 (Опционально, но рекомендуется): Установка Kibana

Kibana — это веб-интерфейс для визуализации данных и управления Elasticsearch. [7]

### 5.1. Установка

Kibana устанавливается из того же репозитория. [3]

```bash
sudo apt install -y kibana
```

### 5.2. Настройка и запуск

Откройте конфигурационный файл Kibana:

```bash
sudo nano /etc/kibana/kibana.yml
```

Убедитесь, что `server.host` установлен в `"localhost"` для локального доступа.

Запустите и включите автозапуск сервиса Kibana:

```bash
sudo systemctl start kibana.service
sudo systemctl enable kibana.service
```

### 5.3. Проверка

Откройте веб-браузер и перейдите по адресу `http://localhost:5601`. Вы должны увидеть стартовую страницу Kibana. [15]

## Заключение

Вы успешно установили и настроили Elasticsearch и Kibana на вашем сервере с Ubuntu 24.04. Теперь система готова к индексации данных, как описано в скрипте `scripts/index_data.py`.