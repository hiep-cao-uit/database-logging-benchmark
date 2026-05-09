# 3DB Distributed Logging Benchmark UI

Ứng dụng Streamlit này convert script insert benchmark ClickHouse, TimescaleDB và InfluxDB thành giao diện web.

## Cài dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy giao diện

```bash
streamlit run app.py
```

Mở URL Streamlit in ra trong terminal, thường là `http://localhost:8501`.

## Chức năng

- Hiển thị default input giống script gốc.
- Cho phép chỉnh DB credentials, số dòng, batch size, Influx chunk, tần suất verify.
- Log realtime ra giao diện.
- Ghi log ra file nếu bật `Ghi log ra file`.
- Hiển thị bảng insert time, storage size, lookup/search metrics, distribution stats.
- Vẽ biểu đồ insert time, rows/sec, lookup/search và phân bố `BusinessKey`, `AppId`, `LogLevel`.

## Lưu ý

- App giả định schema/table đã tồn tại giống script gốc:
  - ClickHouse: `DistributedLogging`
  - TimescaleDB: `distributed_logging`
  - InfluxDB bucket: `DistributedLogging`
- Storage size của InfluxDB dùng lệnh `docker exec <container> du -sh /var/lib/influxdb2`, nên cần đúng tên container.
- Checkbox `Xóa data cũ trước khi insert` sẽ truncate ClickHouse, truncate TimescaleDB và xóa/tạo lại InfluxDB bucket.






python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address localhost