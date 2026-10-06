<div align="center">

# 🛒 Grocery Stock System
### ระบบสต็อกสินค้าร้านขายของชำ

*จัดการสินค้า หมวดหมู่ และการรับสินค้าเข้าคลัง ผ่านเทอร์มินัล เก็บข้อมูลแบบ Binary*

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-Binary%20Fixed--Length-orange)
![Encoding](https://img.shields.io/badge/Encoding-UTF--8-green)
![Version](https://img.shields.io/badge/Version-1.0-blue)
![Dependencies](https://img.shields.io/badge/Dependencies-None-brightgreen)

</div>

---

## ✨ Features

| เมนู | ความสามารถ |
|:---:|---|
| **1** ➕ Add | เพิ่มหมวดหมู่ / เพิ่มสินค้า / บันทึกการรับสินค้าเข้าสต็อก |
| **2** ✏️ Update | แก้ไขข้อมูลสินค้า / หมวดหมู่ |
| **3** 🗑️ Delete | ลบสินค้า / หมวดหมู่ (Soft Delete ข้อมูลไม่หายจริง) |
| **4** 🔍 View & Search | ดูสินค้า ค้นหาตามหมวดหมู่ / สินค้า / ผู้จำหน่าย พร้อมสถิติ |
| **5** 📦 Stock-In Report | รายงานสินค้าเข้าคลังทั้งหมด + สรุปตามผู้จำหน่าย |
| **6** 🗂️ Category Report | รายงานแยกตามหมวดหมู่ |
| **7** 🏷️ Product Report | รายงานรายสินค้า พร้อมประวัติการรับเข้า |
| **0** 🚪 Exit | ออกจากโปรแกรมอย่างปลอดภัย และสร้างรายงานอัตโนมัติ |

**ของแถม**
- 🇹🇭 รองรับภาษาไทยเต็มรูปแบบ (จัดคอลัมน์ตารางตามความกว้างตัวอักษรจริง)
- ⚠️ แจ้งเตือนสินค้าใกล้หมดสต็อก
- 📄 รายงานถูกคัดลอกไปที่ Desktop และเปิดให้อัตโนมัติ
- 🔄 อัปเกรดไฟล์ข้อมูลรุ่นเก่าให้อัตโนมัติเมื่อเปิดโปรแกรม
- 🧾 บันทึก action log ของแต่ละรอบการทำงานลงในรายงาน

---

## 🚀 Quick Start

```bash
# 1. โคลนโปรเจกต์
git clone https://github.com/ChayaponWan/Project_COMPRO.git
cd Project_COMPRO/main_compro_fix

# 2. รันได้เลย ไม่ต้องติดตั้งอะไรเพิ่ม
python Grocery_stock_system.py
```

> 💡 ใช้แค่ Python Standard Library เท่านั้น (`struct`, `datetime`, `shutil`, ...)

---

## 🖥️ หน้าตาโปรแกรม

```text
==========================================
  Grocery Stock System (ระบบสต็อกสินค้าร้านขายของชำ)
==========================================
1) Add
2) Update
3) Delete
4) View & Search
5) Generate Stock-In Report (รายงานสินค้าเข้าคลัง)
6) Generate Category Report (รายงานแยกตามหมวดหมู่)
7) Generate Product Report (รายงานรายสินค้า)
0) Exit
Select option [0-7]:
```

---

## 🗃️ โครงสร้างไฟล์

```text
main_compro_fix/
├── Grocery_stock_system.py   # โปรแกรมหลัก
├── product.dat               # ข้อมูลสินค้า        (Binary)
├── category.dat              # ข้อมูลหมวดหมู่      (Binary)
├── stockin.dat               # ประวัติรับสินค้าเข้า (Binary)
├── stockin_report.txt        # รายงานสินค้าเข้าคลัง
├── Category_report.txt       # รายงานแยกหมวดหมู่
└── Product_report.txt        # รายงานรายสินค้า
```

---

## 🧬 รูปแบบข้อมูล (Binary Fixed-Length, Little-Endian, UTF-8)

| ไฟล์ | Struct | ฟิลด์ |
|---|---|---|
| `product.dat` | `<i15s150si60sffii` | id, barcode, name, category_id, unit, cost, sell, qty, status |
| `category.dat` | `<i90s150si` | id, name, description, status |
| `stockin.dat` | `<iiiff90si` | import_id, product_id, quantity, cost, total_cost, supplier, import_date |

> ⚠️ ภาษาไทย 1 ตัวอักษร = 3 ไบต์ใน UTF-8 ขนาดฟิลด์ข้อความจึงกว้างกว่าจำนวนตัวอักษรจริง 3 เท่า
> (เช่น ชื่อสินค้าใส่ภาษาไทยได้ประมาณ 50 ตัวอักษร)

---

## 🛠️ Tech Stack

- **Language:** Python 3
- **Storage:** Binary file (`struct`) แบบ fixed-length record
- **Delete:** Soft delete ผ่านฟิลด์ `status` (1 = Active, 0 = Deleted)
- **UI:** Command-line interface

---

## 👤 Author

**ChayaponWan** · [GitHub](https://github.com/ChayaponWan)

<div align="center">

⭐ ถ้าชอบโปรเจกต์นี้ ฝากกดดาวให้ด้วยนะครับ ⭐

</div>
