# Project_COMPRO — ระบบสต็อกสินค้าร้านขายของชำ (Grocery Stock Management System)

โปรแกรมจัดการสต็อกสินค้าสำหรับร้านขายของชำ พัฒนาด้วย **Python 3.10+** โดยใช้เฉพาะ
**Standard Library** (`struct`, `os`, `datetime`, `textwrap`) เก็บข้อมูลลง **ไฟล์ไบนารี**
แบบ fixed-length record (pack/unpack ด้วยโมดูล `struct`, little-endian) ทำงานผ่านเมนู
บนเทอร์มินัลรองรับการทำงานแบบ **CRUD** (Add, Update, Delete, View) ครบทั้ง 3 ตารางข้อมูล

## ฟีเจอร์หลัก

- 📦 **จัดการสินค้า (Product)** — เพิ่ม/แก้ไข/ลบ(soft delete)/ดูข้อมูลสินค้า พร้อมผูกกับหมวดหมู่
- 🏷️ **จัดการหมวดหมู่ (Category)** — เพิ่ม/แก้ไข/ลบ/ดูหมวดหมู่สินค้า
- 📥 **บันทึกรายการนำเข้าคลัง (Stock-In)** — บันทึกการรับสินค้าเข้าคลัง พร้อม**อัปเดตจำนวนคงเหลือของสินค้าอัตโนมัติ**
- 🔍 **ดูข้อมูลแบบละเอียด** — ดูรายการเดียว / ดูทั้งหมด / ดูแบบกรอง (ตามหมวดหมู่, สินค้าใกล้หมด, เฉพาะ Active) / สถิติสรุป
- 📄 **สร้างรายงาน (report.txt)** — สรุปจำนวนสินค้า Active/Deleted, สถิติสต็อก, ยอดนำเข้า และ log การทำงานล่าสุด
- ✅ **ตรวจสอบความถูกต้องของอินพุต** ทุกจุด (ชนิดข้อมูล, ขนาด byte ของสตริงภาษาไทย/อังกฤษ, การมีอยู่ของ Foreign Key)
- 💾 **บันทึกไฟล์อย่างปลอดภัย** — `flush()` + `os.fsync()` ทุกครั้งที่เขียนไฟล์ และปิดโปรแกรมพร้อมสร้างรายงานอัตโนมัติ

## โครงสร้างไฟล์ในโปรเจกต์

| ไฟล์ | รายละเอียด |
|---|---|
| `grocery_stock.py` | โค้ดหลักของโปรแกรม (เมนู CRUD ทั้งหมด) |
| `product.dat` | ไฟล์ไบนารีเก็บข้อมูลสินค้า |
| `category.dat` | ไฟล์ไบนารีเก็บข้อมูลหมวดหมู่สินค้า |
| `stockin.dat` | ไฟล์ไบนารีเก็บรายการนำเข้าสินค้าเข้าคลัง |
| `report.txt` | ไฟล์รายงานสรุป (สร้างขึ้นเมื่อเลือกเมนู Generate Report หรือ Exit) |

## โครงสร้างข้อมูล (Record Spec)

**ตารางสินค้า (Product)** — `<i15s50si10sffii` (~103 bytes/record)

| Field | ชนิด | ขนาด |
|---|---|---|
| product_id | int | 4 Bytes |
| barcode | str | 15 Bytes |
| name | str | 50 Bytes |
| category_id | int | 4 Bytes |
| unit | str | 10 Bytes |
| cost_price | float | 4 Bytes |
| sell_price | float | 4 Bytes |
| stock_qty | int | 4 Bytes |
| status | int | 4 Bytes (1=Active, 0=Deleted) |

**ตารางหมวดหมู่ (Category)** — `<i30s50si` (88 bytes/record)

| Field | ชนิด | ขนาด |
|---|---|---|
| category_id | int | 4 Bytes |
| category_name | str | 30 Bytes |
| description | str | 50 Bytes |
| status | int | 4 Bytes |

**ตารางรายการนำเข้าคลัง (Stock-In)** — `<iiiff30si` (50 bytes/record)

| Field | ชนิด | ขนาด |
|---|---|---|
| import_id | int | 4 Bytes |
| product_id | int | 4 Bytes |
| quantity | int | 4 Bytes |
| cost_price | float | 4 Bytes |
| total_cost | float | 4 Bytes |
| supplier | str | 30 Bytes |
| import_date | int (timestamp) | 4 Bytes |

## วิธีการติดตั้งและใช้งาน

ไม่ต้องติดตั้งไลบรารีเพิ่มเติม ใช้ได้ทันทีบน Python 3.10 ขึ้นไป

```bash
git clone https://github.com/ChayaponWan/Project_COMPRO.git
cd Project_COMPRO
python3 grocery_stock.py
```

จากนั้นเลือกเมนูตามตัวเลข (1-5, 0) ที่แสดงบนหน้าจอ

## เมนูการทำงาน

```
1) Add       - เพิ่มข้อมูล (สินค้า / หมวดหมู่ / รายการนำเข้าคลัง)
2) Update    - แก้ไขข้อมูล
3) Delete    - ลบข้อมูล (soft delete)
4) View      - ดูข้อมูล (รายการเดียว / ทั้งหมด / กรอง / สถิติ)
5) Generate Report (.txt)
0) Exit      - ออกจากโปรแกรม (บันทึกและสร้างรายงานอัตโนมัติ)
```

## หมายเหตุ

โปรเจกต์นี้พัฒนาขึ้นเพื่อการศึกษา (โครงงาน Python File I/O) โดยเน้นการฝึกใช้งาน
binary file I/O ร่วมกับโมดูล `struct` แทนการใช้ฐานข้อมูลสำเร็จรูป
