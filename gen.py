"""
===============================================================================
  สคริปต์สร้างชุดข้อมูลทดสอบ (Test Data Generator)
  สำหรับระบบสต็อกสินค้าร้านขายของชำ (Grocery Stock System)
===============================================================================

วิธีใช้:
    python gen.py

จะสร้างไฟล์ category.dat, product.dat, stockin.dat ใหม่ทับของเดิม
(ถ้ามีไฟล์เดิมอยู่ จะสำรองไว้เป็น *_backup_before_testdata.dat ก่อน)
"""

import struct
import os
import shutil
import random
import datetime

# ---- โครงสร้างตรงกับ grocery_stock.py ----
ENDIAN = "<"  # little-endian

CATEGORY_FORMAT = ENDIAN + "i30s50si"      # id, category_name, description, status
PRODUCT_FORMAT  = ENDIAN + "i15s50si10sffii" # id, barcode, name, category_id, unit, cost, sell, qty, status
STOCKIN_FORMAT  = ENDIAN + "iiiff30si"      # import_id, product_id, quantity, cost_price, total_cost, supplier, import_date

CATEGORY_SIZE = struct.calcsize(CATEGORY_FORMAT)
PRODUCT_SIZE  = struct.calcsize(PRODUCT_FORMAT)
STOCKIN_SIZE  = struct.calcsize(STOCKIN_FORMAT)

CATEGORY_FILE = "category.dat"
PRODUCT_FILE  = "product.dat"
STOCKIN_FILE  = "stockin.dat"

STATUS_ACTIVE = 1
STATUS_DELETED = 0

random.seed(2569)  # ตั้ง seed ให้ผลลัพธ์ซ้ำเดิมได้ทุกครั้ง (reproducible)

def encode_fixed(s: str, size: int) -> bytes:
    """เข้ารหัสสตริงให้พอดีขนาด โดยไม่ตัดกลางตัวอักษรหลายไบต์ (กันภาษาไทยเพี้ยน)"""
    b = s.encode("utf-8")
    if len(b) > size:
        cut = size
        while cut > 0:
            try:
                b[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1
        b = b[:cut]
    return b.ljust(size, b"\x00")

def backup(fname):
    """สำรองไฟล์เดิมถ้ามีอยู่"""
    if os.path.exists(fname):
        backup_name = fname.replace(".dat", "_backup_before_testdata.dat")
        shutil.copy(fname, backup_name)
        print(f"  สำรอง {fname} -> {backup_name}")

# ============================================================
# ข้อมูลตั้งต้นสำหรับสุ่ม
# ============================================================

CATEGORIES_DATA = [
    ("เครื่องดื่ม", "น้ำดื่ม น้ำหวาน กาแฟ และเครื่องดื่มบรรจุขวด"),
    ("ขนมขบเคี้ยว", "มันฝรั่งทอด บิสกิต ขนมอบกรอบ"),
    ("อาหารแห้ง/บะหมี่", "บะหมี่กึ่งสำเร็จรูป อาหารกระป๋อง เครื่องปรุง"),
    ("ของใช้ในบ้าน", "น้ำยาล้างจาน ผงซักฟอก กระดาษชำระ"),
    ("ของใช้ส่วนตัว", "สบู่ แชมพู ยาสีฟัน แปรงสีฟัน"),
    ("ผลิตภัณฑ์นม", "นมสด นมเปรี้ยว โยเกิร์ต เนย"),
    ("อาหารสด/แช่เย็น", "ไข่ไก่ ไส้กรอก ลูกชิ้น"),
    ("เครื่องปรุงรส", "น้ำปลา ซีอิ๊ว น้ำตาล ซอสมะเขือเทศ"),
    ("เครื่องเขียน/เบ็ดเตล็ด", "ปากกา สมุด ถุงขยะ เทปกาว"),
    ("เครื่องดื่มแอลกอฮอล์", "เบียร์ สุรา (หมวดพิเศษ)"),
]

PRODUCT_NAMES = [
    ("น้ำดื่มตราสยาม 600ml", "ขวด", 5.0, 10.0),
    ("โค้กออริจินัล 325ml", "กระป๋อง", 10.0, 15.0),
    ("อิชิตันชาเขียว 420ml", "ขวด", 12.0, 20.0),
    ("นมสดพาสเจอร์ไรส์ 200ml", "กล่อง", 8.0, 12.5),
    ("กาแฟกระป๋องเบอร์ดี้", "กระป๋อง", 11.0, 17.0),
    ("เลย์รสมันฝรั่งแท้ 42g", "ซอง", 15.0, 20.0),
    ("ปาปริก้ากรอบ 50g", "ซอง", 12.0, 18.0),
    ("ฮานามิข้าวเกรียบกุ้ง", "ซอง", 10.0, 15.0),
    ("มาม่าต้มยำกุ้ง 55g", "ซอง", 5.0, 7.0),
    ("ไวไวหอยลายผัดฉ่า", "ซอง", 5.5, 8.0),
    ("ปลากระป๋องสามแม่ครัว", "กระป๋อง", 14.0, 22.0),
    ("น้ำมันพืชองุ่น 1 ลิตร", "ขวด", 42.0, 55.0),
    ("น้ำปลาทิพรส 700ml", "ขวด", 26.0, 32.0),
    ("ข้าวหอมมะลิ 5 กก.", "ถุง", 160.0, 210.0),
    ("สบู่ลักส์ 105g", "ก้อน", 12.0, 18.0),
    ("แชมพูรีจอยส์ 170ml", "ขวด", 35.0, 49.0),
    ("ยาสีฟันคอลเกต 150g", "หลอด", 38.0, 55.0),
    ("ผงซักฟอกบรีสเอกเซล 800g", "ถุง", 65.0, 89.0),
    ("น้ำยาล้างจานไลปอนเอฟ 500ml", "ถุง", 18.0, 25.0),
    ("ทิชชู่ซีเล็คแพ็ค 6", "แพ็ค", 32.0, 45.0),
]

SUPPLIERS = [
    "บริษัท บิ๊กซี ซัพพลาย จำกัด",
    "บจก. ไทยยูนียน โฮลดิ้ง",
    "ร้านค้าส่งเจ๊พร ตลาดไท",
    "บริษัท ซีพี ออลล์ ดีสทริบิวชั่น",
    "สยามแม็คโคร สาขาแจ้งวัฒนะ",
    "ศูนย์กระจายสินค้าปทุมธานี",
]

def gen_categories():
    """สร้างหมวดหมู่ 12 หมวดหมู่ (10 active + 2 soft-deleted)"""
    records = []
    active_cat_ids = []
    
    for i in range(12):
        cat_id = i + 1
        if i < len(CATEGORIES_DATA):
            name, desc = CATEGORIES_DATA[i]
        else:
            name = f"หมวดหมู่ทดสอบ {i+1}"
            desc = "หมวดหมู่สำหรับทดสอบระบบเพิ่มเติม"
        
        status = STATUS_DELETED if i in (8, 11) else STATUS_ACTIVE  # soft delete 2 หมวด
        if status == STATUS_ACTIVE:
            active_cat_ids.append(cat_id)

        records.append(struct.pack(
            CATEGORY_FORMAT, cat_id, encode_fixed(name, 30), encode_fixed(desc, 50), status
        ))
    return records, active_cat_ids

def gen_products(valid_cat_ids):
    """สร้างสินค้า 60 รายการ (55 active + 5 soft-deleted)"""
    records = []
    product_ids = []
    used_barcodes = set()
    
    for i in range(60):
        prod_id = 1001 + i
        
        # บาร์โค้ด 13-15 หลัก ห้ามซ้ำ
        while True:
            barcode = f"885{random.randint(1000000000, 9999999999)}"
            if barcode not in used_barcodes:
                used_barcodes.add(barcode)
                break

        # สุ่มข้อมูลสินค้าจากชุดตัวอย่าง
        base_name, unit, base_cost, base_sell = PRODUCT_NAMES[i % len(PRODUCT_NAMES)]
        name = f"{base_name} ({i+1})"
        
        # กรณีขอบ: ชื่อสินค้าภาษาไทยยาวเกินขนาดฟิลด์ 50 ไบต์
        if i == 7:
            name = "น้ำมันพืชผสมผ่านกรรมวิธีตรามรกตสกัดพิเศษขนาดประหยัดสุดคุ้ม"
        # กรณีขอบ: หน่วยนับยาวเต็มฟิลด์พอดี
        if i == 12:
            unit = "กล่องใหญ่"

        cat_id = random.choice(valid_cat_ids)
        
        # กรณีขอบ: ราคาทุน/ขายเป็น 0 หรือสต็อกเป็น 0
        if i == 3:
            qty = 0  # สินค้าหมดสต็อก
            cost_price = base_cost
            sell_price = base_sell
        elif i == 15:
            cost_price = 0.0  # สินค้าของแถม/โปรโมชั่น
            sell_price = 0.0
            qty = 20
        else:
            cost_price = base_cost
            sell_price = base_sell
            qty = random.randint(1, 100)

        status = STATUS_DELETED if i in (5, 18, 29, 42, 53) else STATUS_ACTIVE  # soft delete 5 ชิ้น
        
        records.append(struct.pack(
            PRODUCT_FORMAT, prod_id, encode_fixed(barcode, 15), encode_fixed(name, 50),
            cat_id, encode_fixed(unit, 10), cost_price, sell_price, qty, status
        ))
        
        if status == STATUS_ACTIVE:
            product_ids.append((prod_id, cost_price))

    return records, product_ids

def gen_stockins(active_products):
    """สร้างรายการนำเข้าคลัง (Stock-In) 80 รายการ"""
    records = []
    base_time = datetime.datetime(2026, 8, 1, 8, 30, 0)

    for import_id in range(5001, 5081):
        prod_id, default_cost = random.choice(active_products)
        qty = random.randint(5, 100)
        
        # สุ่มราคาทุนตามสินค้า หรือมีส่วนลดบ้าง
        cost_price = default_cost if default_cost > 0 else 5.0
        total_cost = qty * cost_price
        supplier = random.choice(SUPPLIERS)
        
        # วันที่นำเข้าทยอยเพิ่มขึ้นตามเวลา
        import_date = int((base_time + datetime.timedelta(hours=(import_id - 5000) * 12)).timestamp())

        records.append(struct.pack(
            STOCKIN_FORMAT, import_id, prod_id, qty, cost_price, total_cost,
            encode_fixed(supplier, 30), import_date
        ))
    return records

def main():
    print("=== สร้างชุดข้อมูลทดสอบร้านขายของชำ (Grocery Stock Test Data Generator) ===\n")
    print("สำรองไฟล์เดิม (ถ้ามี):")
    for fname in (CATEGORY_FILE, PRODUCT_FILE, STOCKIN_FILE):
        backup(fname)

    print("\nกำลังสร้างข้อมูล...")
    cat_records, valid_cat_ids = gen_categories()
    prod_records, active_products = gen_products(valid_cat_ids)
    stockin_records = gen_stockins(active_products)

    with open(CATEGORY_FILE, "wb") as f:
        for r in cat_records:
            f.write(r)
            
    with open(PRODUCT_FILE, "wb") as f:
        for r in prod_records:
            f.write(r)
            
    with open(STOCKIN_FILE, "wb") as f:
        for r in stockin_records:
            f.write(r)

    print(f"\nสร้างข้อมูลเสร็จเรียบร้อย:")
    print(f"  {CATEGORY_FILE:<18} : {len(cat_records):>3} records "
          f"({os.path.getsize(CATEGORY_FILE):>6} ไบต์ @ {CATEGORY_SIZE} ไบต์/record)")
    print(f"  {PRODUCT_FILE:<18} : {len(prod_records):>3} records "
          f"({os.path.getsize(PRODUCT_FILE):>6} ไบต์ @ {PRODUCT_SIZE} ไบต์/record)")
    print(f"  {STOCKIN_FILE:<18} : {len(stockin_records):>3} records "
          f"({os.path.getsize(STOCKIN_FILE):>6} ไบต์ @ {STOCKIN_SIZE} ไบต์/record)")
    
    print(f"\n  รวมทั้งหมด : {len(cat_records) + len(prod_records) + len(stockin_records)} records")
    print("\nกรณีขอบที่รวมอยู่ในชุดข้อมูล:")
    print("  - หมวดหมู่ที่ถูก Soft Delete 2 หมวด / สินค้าที่ถูก Soft Delete 5 รายการ")
    print("  - ชื่อสินค้าภาษาไทยยาวเกินขนาดฟิลด์ (ทดสอบการตัดข้อความแบบปลอดภัย)")
    print("  - สินค้าที่มีจำนวนคงเหลือเป็น 0 (สินค้าหมด)")
    print("  - สินค้าที่ราคาทุนและราคาขายเป็น 0.0 บาท (ของแถม)")
    print("  - บาร์โค้ดไม่ซ้ำกันตามระบบมาตรฐาน")
    print("\nรันโปรแกรมหลักด้วย: python grocery_stock.py")

if __name__ == "__main__":
    main()