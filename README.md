# 3DB Distributed Logging Benchmark UI

Ứng dụng Streamlit để generate dữ liệu logging và benchmark insert/query đồng thời trên 3 database: ClickHouse, TimescaleDB và InfluxDB.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy ứng dụng

```bash
streamlit run app.py --server.port 8501 --server.address localhost
```

Mở URL Streamlit in ra trong terminal (mặc định `http://localhost:8501`).

## Cấu hình trong Sidebar

- **ClickHouse**: `CH_HOST`, `CH_PORT`, `CH_USER`, `CH_PASSWORD`
- **TimescaleDB**: `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DB`
- **InfluxDB**: `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET`, `Influx Docker container`
- **Run config**:
  - `TOTAL_ROWS`: tổng số dòng cần insert
  - `BATCH_SIZE`: số dòng mỗi batch
  - `INFLUX_CHUNK`: chunk size khi ghi InfluxDB
  - `Verify every N batches`: tần suất chạy nhóm query verify
  - `Xóa data cũ trước khi insert`
  - `Ghi log ra file` + `OUTPUT_FILE`

## Ứng dụng làm gì khi bấm `Run benchmark`

1. Kết nối đồng thời 3 database.
2. Nếu bật `Xóa data cũ trước khi insert`:
   - ClickHouse: `TRUNCATE TABLE DistributedLogging`
   - TimescaleDB: `TRUNCATE TABLE distributed_logging`
   - InfluxDB: xóa và tạo lại bucket với retention 90 ngày
3. Generate dữ liệu giả lập logging theo batch.
4. Insert song song vào 3 DB bằng `ThreadPoolExecutor`.
5. Theo chu kỳ verify:
   - Lấy storage size của từng DB
   - Chạy các nhóm query benchmark:
     - `point_lookup`
     - `trace_lookup`
     - `free_text`
     - thống kê phân bố `AppId`, `LogLevel`, `BusinessKey`
6. Hiển thị bảng + biểu đồ ngay trên UI, đồng thời stream log realtime.

## Kết quả hiển thị

- Bảng/biểu đồ thời gian insert theo số dòng đã insert (`rows_done`)
- Bảng storage size theo từng DB
- Bảng/biểu đồ thời gian query cho `point_lookup`, `trace_lookup`, `free_text`
- Bảng/biểu đồ phân bố `AppId`, `LogLevel`, `BusinessKey` và thời gian query thống kê
- Bảng tổng hợp `Verify summary`

## Điều kiện dữ liệu/schemas

App **không tự tạo schema bảng chính** cho ClickHouse/TimescaleDB. Cần chuẩn bị sẵn:

- ClickHouse table: `DistributedLogging`
  - Các cột được insert: `id`, `traceId`, `appId`, `logLevel`, `businessKey`, `logTime`, `message`, `rawData`
- TimescaleDB table: `distributed_logging`
  - Các cột được insert: `id`, `trace_id`, `app_id`, `log_level`, `business_key`, `log_time`, `message`, `raw_data`
- InfluxDB measurement dùng trong benchmark: `distributed_logging` (ghi vào bucket đã cấu hình)

## Lưu ý vận hành

- Storage size InfluxDB được lấy bằng lệnh Docker:
  - `docker exec <influx_container> du -sh /var/lib/influxdb2`
  - Vì vậy tên container phải đúng với môi trường chạy.
- Nếu `Ghi log ra file` bật, log được ghi vào `OUTPUT_FILE` (mặc định `generate_3db_output.txt` tại thư mục project).
- Trong một số trường hợp timeout ghi InfluxDB, app sẽ tự retry tối đa 5 lần cho mỗi chunk.