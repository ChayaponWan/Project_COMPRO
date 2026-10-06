from datetime import datetime
import os
import shutil
import struct
import subprocess
from typing import List, Tuple
import unicodedata

APP_VERSION = "1.0"

# ไฟล์ข้อมูล (Binary fixed-length) หมายเหตุ: ภาษาไทย 1 ตัวอักษร = 3 ไบต์ใน UTF-8
# ขนาดฟิลด์จึงกว้างกว่าจำนวนตัวอักษรที่ต้องการ 3 เท่า (ไฟล์ .dat รุ่นเก่าอ่านด้วยโค้ดนี้ไม่ได้ ต้องย้ายข้อมูลก่อน)
PRODUCT_FILE = "product.dat"
CATEGORY_FILE = "category.dat"
STOCKIN_FILE = "stockin.dat"

# product : id, barcode, name, category_id, unit, cost, sell, qty, status
PRODUCT_STRUCT = struct.Struct("<i15s150si60sffii")
# category: id, name, description, status
CATEGORY_STRUCT = struct.Struct("<i90s150si")
# stockin : import_id, product_id, quantity, cost, total_cost, supplier, import_date
STOCKIN_STRUCT = struct.Struct("<iiiff90si")

REPORT_FILE = "stockin_report.txt"
CATEGORY_REPORT_FILE = "Category_report.txt"
PRODUCT_REPORT_FILE = "Product_report.txt"

STATUS_ACTIVE = 1
STATUS_DELETED = 0
LOW_STOCK_LIMIT = 5

# ตำแหน่งฟิลด์ในแต่ละ record
PROD_ID, PROD_BARCODE, PROD_NAME, PROD_CAT, PROD_UNIT = 0, 1, 2, 3, 4
PROD_COST, PROD_SELL, PROD_QTY, PROD_STATUS = 5, 6, 7, 8

CAT_ID, CAT_NAME, CAT_DESC, CAT_STATUS = 0, 1, 2, 3

SIN_ID, SIN_PID, SIN_QTY, SIN_COST, SIN_TOTAL, SIN_SUPPLIER, SIN_DATE = (
    0, 1, 2, 3, 4, 5, 6,
)

# ขนาดฟิลด์ข้อความ (หน่วย: ไบต์)
BARCODE_BYTES = 15
NAME_BYTES = 150       # ชื่อสินค้า  (ไทยได้ประมาณ 50 ตัวอักษร)
UNIT_BYTES = 60        # หน่วยนับ    (ไทยได้ประมาณ 20 ตัวอักษร)
CAT_NAME_BYTES = 90    # ชื่อหมวดหมู่ (ไทยได้ประมาณ 30 ตัวอักษร)
DESC_BYTES = 150       # คำอธิบายหมวดหมู่ (ไทยได้ประมาณ 50 ตัวอักษร)
SUPPLIER_BYTES = 90    # ชื่อผู้จำหน่าย (ไทยได้ประมาณ 30 ตัวอักษร)

action_log: List[str] = []  # บันทึกการทำงานในรอบนี้ ใช้แสดงในรายงาน


# --- String / Display helpers ---

def pack_string(s: str, max_bytes: int) -> bytes:
    encoded = s.strip().encode("utf-8")
    if len(encoded) > max_bytes:
        encoded = (
            encoded[:max_bytes].decode("utf-8", errors="ignore").encode("utf-8")
        )
    return encoded.ljust(max_bytes, b"\x00")


def unpack_string(b: bytes) -> str:
    return b.decode("utf-8", errors="ignore").rstrip("\x00").strip()


def clean_thai_str(text):
    return unicodedata.normalize("NFC", str(text))


def display_width(text):
    text = clean_thai_str(text)
    width = 0
    for ch in text:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        width += 1
    return width


def fit_to_width(text, width):
    text = clean_thai_str(text)
    result = []
    current_width = 0

    for ch in text:
        if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            char_width = 0
        else:
            char_width = 1

        if current_width + char_width > width:
            break

        result.append(ch)
        current_width += char_width

    return "".join(result), current_width


def pad_str(s, width, align="left"):
    text, current_width = fit_to_width(s, width)
    padding = width - current_width

    if align == "right":
        return (" " * padding) + text
    elif align == "center":
        left = padding // 2
        right = padding - left
        return (" " * left) + text + (" " * right)
    else:
        return text + (" " * padding)


def now_ts() -> int:
    return int(datetime.now().timestamp())


def fmt_ts(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "-"


def status_text(status: int) -> str:
    return "Active" if status == STATUS_ACTIVE else "Deleted"


def log_action(msg: str):
    action_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# --- Binary file helpers ---

def read_file(filename: str, struct_def: struct.Struct) -> List[Tuple]:
    records = []
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(struct_def.size)
                if not chunk:
                    break
                if len(chunk) == struct_def.size:
                    records.append(struct_def.unpack(chunk))
    return records


def write_file(filename: str, struct_def: struct.Struct, records: List[Tuple]):
    with open(filename, "wb") as f:
        for rec in records:
            f.write(struct_def.pack(*rec))
        f.flush()
        os.fsync(f.fileno())


def append_record(
    filename: str, struct_def: struct.Struct, record: Tuple
) -> None:
    with open(filename, "ab") as f:
        f.write(struct_def.pack(*record))
        f.flush()
        os.fsync(f.fileno())


# --- อัปเกรดไฟล์ .dat รุ่นเก่า (ฟิลด์แคบ) อัตโนมัติ ---
# ป้องกัน error/ข้อมูลเพี้ยนเมื่อเปิดไฟล์เก่าด้วยโค้ดรุ่นนี้ หรือไฟล์ที่ปนกันสองรูปแบบ

OLD_PRODUCT_STRUCT = struct.Struct("<i15s50si10sffii")
OLD_CATEGORY_STRUCT = struct.Struct("<i30s50si")
OLD_STOCKIN_STRUCT = struct.Struct("<iiiff30si")


def _parse(buf, st):
    return [st.unpack_from(buf, i) for i in range(0, len(buf) - st.size + 1, st.size)]


def upgrade_data_file(filename, new_s, old_s, ok, id_idx) -> bool:
    """แปลงไฟล์เป็นรูปแบบใหม่ถ้าจำเป็น คืน True ถ้ามีการแปลง
    รองรับ: ไฟล์เก่าล้วน, ไฟล์ที่ปนกัน (record เก่าตามด้วย record ใหม่), และ id ซ้ำ"""
    if not os.path.exists(filename):
        return False
    data = open(filename, "rb").read()
    if not data:
        return False
    if len(data) % new_s.size == 0 and all(ok(r) for r in _parse(data, new_s)):
        return False

    recs = None
    for k in range(len(data) // old_s.size, -1, -1):          # k = จำนวน record เก่าที่นำหน้า
        rest = len(data) - k * old_s.size
        if rest % new_s.size:
            continue
        old_part = _parse(data[: k * old_s.size], old_s)
        new_part = _parse(data[k * old_s.size:], new_s)
        if all(ok(r) for r in old_part) and all(ok(r) for r in new_part):
            recs = [new_s.unpack(new_s.pack(*r)) for r in old_part] + new_part
            break
    if recs is None:
        print(f"[Warning] {filename}: unknown file format, left unchanged.")
        return False

    seen, max_id = set(), max(r[id_idx] for r in recs)
    fixed = []
    for r in recs:                                             # แก้ id ซ้ำ (ถ้ามี)
        if r[id_idx] in seen:
            max_id += 1
            r = list(r)
            print(f"[Info] {filename}: duplicate id {r[id_idx]} renumbered to {max_id}")
            r[id_idx] = max_id
            r = tuple(r)
        seen.add(r[id_idx])
        fixed.append(r)

    backup = filename + ".bak"
    if not os.path.exists(backup):
        shutil.copyfile(filename, backup)
    write_file(filename, new_s, fixed)
    print(f"[Info] {filename}: upgraded to the new format ({len(fixed)} records, backup: {backup})")
    return True


def upgrade_all_data_files():
    upgrade_data_file(CATEGORY_FILE, CATEGORY_STRUCT, OLD_CATEGORY_STRUCT,
                      lambda r: r[0] > 0 and r[3] in (0, 1), CAT_ID)
    upgrade_data_file(PRODUCT_FILE, PRODUCT_STRUCT, OLD_PRODUCT_STRUCT,
                      lambda r: r[0] > 0 and r[8] in (0, 1), PROD_ID)
    upgrade_data_file(STOCKIN_FILE, STOCKIN_STRUCT, OLD_STOCKIN_STRUCT,
                      lambda r: r[0] > 0 and r[1] > 0 and r[2] >= 0, SIN_ID)



def find_by_id(records: List[Tuple], id_idx: int, value):
    for i, r in enumerate(records):
        if r[id_idx] == value:
            return i, r
    return None, None


def next_id(records: List[Tuple], id_idx: int, start: int) -> int:
    """Auto-increment: max id (รวมที่ถูกลบ) + 1"""
    max_id = start - 1
    for r in records:
        if r[id_idx] > max_id:
            max_id = r[id_idx]
    return max_id + 1


def soft_delete(filename, struct_def, records, id_idx, status_idx, value) -> bool:
    i, rec = find_by_id(records, id_idx, value)
    if rec is None or rec[status_idx] == STATUS_DELETED:
        return False
    rec = list(rec)
    rec[status_idx] = STATUS_DELETED
    records[i] = tuple(rec)
    write_file(filename, struct_def, records)
    return True


# --- Input helpers (คืน None เมื่อผิดพลาด / คืน "" เมื่อเว้นว่างและอนุญาต) ---

def ask_int(prompt, min_val=None, max_val=None, allow_blank=False, label="Value"):
    raw = input(prompt).strip()
    if raw == "" and allow_blank:
        return ""
    try:
        val = int(raw)
    except ValueError:
        print(f"[Error] {label} must be an integer.")
        return None
    if min_val is not None and val < min_val:
        print(f"[Error] {label} must not be less than {min_val}.")
        return None
    if max_val is not None and val > max_val:
        print(f"[Error] {label} must not be more than {max_val}.")
        return None
    return val


def ask_float(prompt, min_val=None, allow_blank=False, label="Value"):
    raw = input(prompt).strip()
    if raw == "" and allow_blank:
        return ""
    try:
        val = float(raw)
    except ValueError:
        print(f"[Error] {label} must be a number.")
        return None
    if min_val is not None and val < min_val:
        print(f"[Error] {label} must not be less than {min_val}.")
        return None
    return val


def ask_str(prompt, max_bytes, allow_blank=False, label="Value"):
    raw = input(prompt).strip()
    if raw == "":
        if allow_blank:
            return ""
        print(f"[Error] {label} cannot be empty.")
        return None
    if len(raw.encode("utf-8")) > max_bytes:
        print(
            f"[Error] {label} is too long: {len(raw.encode('utf-8'))} bytes "
            f"(max {max_bytes} bytes, about {max_bytes // 3} Thai characters). "
            "Please enter a shorter text."
        )
        return None
    return raw


# --- Table helpers (ใช้ทั้งหน้าจอและรายงาน) ---

def make_table_helpers(w):
    """ตารางแบบเปิดท้าย: ทุกคอลัมน์ยกเว้นคอลัมน์สุดท้ายต้องเป็นตัวเลข/อังกฤษ
    ส่วนคอลัมน์สุดท้ายใส่ข้อความไทยได้ (ไม่เติมช่องว่าง จึงไม่ทำให้เส้นเหลื่อม)
    เหตุผล: Notepad วาดตัวอักษรไทยกว้างไม่เท่ากัน จึงจัดคอลัมน์ด้วยการนับตัวอักษรไม่ได้"""
    def draw_border():
        return "+" + "+".join("-" * (width + 2) for width in w) + "+"

    def draw_row(values):
        cells = []
        last = len(w) - 1
        for i, width in enumerate(w):
            value = str(values[i]) if i < len(values) else ""
            if i < last:
                cells.append(pad_str(value, width))
            else:
                cells.append(clean_thai_str(value))
        return "| " + " | ".join(cells)

    return draw_border, draw_row


def render_table(headers, w, rows):
    draw_border, draw_row = make_table_helpers(w)
    lines = [draw_border(), draw_row(headers), draw_border()]
    for r in rows:
        lines.append(draw_row(r))
    lines.append(draw_border())
    return lines


def print_table(headers, w, rows):
    for line in render_table(headers, w, rows):
        print(line)


def category_label(categories, cid):
    _, c = find_by_id(categories, CAT_ID, cid)
    name = unpack_string(c[CAT_NAME]) if c else "Unknown"
    return f"[{cid}] {name}"


# หมายเหตุ: คอลัมน์สุดท้ายของทุกตารางเป็นช่องข้อความ (ไทยได้)
PRODUCT_HEADERS = [
    "ID", "Barcode", "Cost", "Sell", "Qty", "Status", "Cat.ID", "Name [Unit]",
]
PRODUCT_W = [6, 15, 9, 9, 7, 8, 7, 40]


def product_row(p, categories=None):
    return [
        p[PROD_ID],
        unpack_string(p[PROD_BARCODE]),
        f"{p[PROD_COST]:.2f}",
        f"{p[PROD_SELL]:.2f}",
        p[PROD_QTY],
        status_text(p[PROD_STATUS]),
        p[PROD_CAT],
        f"{unpack_string(p[PROD_NAME])} [{unpack_string(p[PROD_UNIT])}]",
    ]


CATEGORY_HEADERS = ["ID", "Status", "Name - Description"]
CATEGORY_W = [6, 8, 60]


def category_row(c):
    name = unpack_string(c[CAT_NAME])
    desc = unpack_string(c[CAT_DESC])
    return [
        c[CAT_ID],
        status_text(c[CAT_STATUS]),
        f"{name} - {desc}" if desc else name,
    ]


STOCKIN_HEADERS = [
    "Import ID", "Product ID", "Qty", "Cost/Unit", "Total Cost", "Date", "Supplier",
]
STOCKIN_W = [9, 10, 7, 10, 12, 16, 30]


def stockin_row(s, products=None):
    return [
        s[SIN_ID],
        s[SIN_PID],
        s[SIN_QTY],
        f"{s[SIN_COST]:.2f}",
        f"{s[SIN_TOTAL]:.2f}",
        fmt_ts(s[SIN_DATE]),
        unpack_string(s[SIN_SUPPLIER]),
    ]


def calc_product_stats(products):
    actives = [p for p in products if p[PROD_STATUS] == STATUS_ACTIVE]
    stats = {
        "total": len(products),
        "active": len(actives),
        "deleted": len(products) - len(actives),
        "total_qty": 0,
        "low_stock": [],
        "avg_sell": 0.0,
    }
    if actives:
        stats["total_qty"] = sum(p[PROD_QTY] for p in actives)
        stats["low_stock"] = [p for p in actives if p[PROD_QTY] <= LOW_STOCK_LIMIT]
        stats["avg_sell"] = sum(p[PROD_SELL] for p in actives) / len(actives)
    return stats


# --- Add ---

def add_category():
    print("\n --- Add Category ---")
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)

    name = ask_str("Category Name: ", CAT_NAME_BYTES, label="Category Name")
    if name is None:
        return
    desc = ask_str("Description (optional): ", DESC_BYTES, allow_blank=True, label="Description")
    if desc is None:
        return

    cid = next_id(categories, CAT_ID, 1)
    record = (cid, pack_string(name, CAT_NAME_BYTES), pack_string(desc, DESC_BYTES), STATUS_ACTIVE)
    append_record(CATEGORY_FILE, CATEGORY_STRUCT, record)
    log_action(f"Add Category id={cid} name='{name}'")
    print(f"Category data saved successfully (ID: {cid}).")


def pick_active_category(prompt="Category ID: ", allow_blank=False):
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    actives = [c for c in categories if c[CAT_STATUS] == STATUS_ACTIVE]
    if not actives:
        print("[Error] No category in system. Please add a category first.")
        return None

    print("  Available categories:")
    for c in actives:
        print(f"    [{c[CAT_ID]}] {unpack_string(c[CAT_NAME])}")

    cid = ask_int(prompt, allow_blank=allow_blank, label="Category ID")
    if cid is None or cid == "":
        return cid
    if not any(c[CAT_ID] == cid for c in actives):
        print("[Error] Category ID not found or already deleted.")
        return None
    return cid


def add_product():
    print("\n --- Add Product ---")
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)

    barcode = ask_str("Barcode: ", BARCODE_BYTES, label="Barcode")
    if barcode is None:
        return
    name = ask_str("Product Name: ", NAME_BYTES, label="Product Name")
    if name is None:
        return
    cat_id = pick_active_category()
    if cat_id is None:
        return
    unit = ask_str("Unit (เช่น ชิ้น, ขวด, กก.): ", UNIT_BYTES, label="Unit")
    if unit is None:
        return
    cost = ask_float("Cost Price: ", min_val=0, label="Cost Price")
    if cost is None:
        return
    sell = ask_float("Sell Price: ", min_val=0, label="Sell Price")
    if sell is None:
        return
    qty = ask_int("Initial Stock Qty: ", min_val=0, label="Stock Qty")
    if qty is None:
        return

    pid = next_id(products, PROD_ID, 1001)
    record = (
        pid,
        pack_string(barcode, BARCODE_BYTES),
        pack_string(name, NAME_BYTES),
        cat_id,
        pack_string(unit, UNIT_BYTES),
        cost,
        sell,
        qty,
        STATUS_ACTIVE,
    )
    append_record(PRODUCT_FILE, PRODUCT_STRUCT, record)
    log_action(f"Add Product id={pid} name='{name}'")
    print(f"Product data saved successfully (ID: {pid}).")


def add_stockin():
    print("\n --- Add Stock-In ---")
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)

    pid = ask_int("Product ID: ", label="Product ID")
    if pid is None:
        return
    p_idx, prod = find_by_id(products, PROD_ID, pid)
    if prod is None or prod[PROD_STATUS] == STATUS_DELETED:
        print("[Error] Product ID not found or already deleted.")
        return

    qty = ask_int("Quantity: ", min_val=1, label="Quantity")
    if qty is None:
        return
    cost = ask_float(
        f"Cost per unit (current={prod[PROD_COST]:.2f}, Enter=keep current): ",
        min_val=0,
        allow_blank=True,
        label="Cost per unit",
    )
    if cost is None:
        return
    if cost == "":
        cost = prod[PROD_COST]
    supplier = ask_str("Supplier: ", SUPPLIER_BYTES, label="Supplier")
    if supplier is None:
        return

    import_id = next_id(stockins, SIN_ID, 5001)
    total_cost = qty * cost
    record = (
        import_id,
        pid,
        qty,
        cost,
        total_cost,
        pack_string(supplier, SUPPLIER_BYTES),
        now_ts(),
    )
    append_record(STOCKIN_FILE, STOCKIN_STRUCT, record)

    # อัปเดตจำนวนคงเหลือและราคาทุนของสินค้า
    prod = list(prod)
    prod[PROD_QTY] += qty
    prod[PROD_COST] = cost
    products[p_idx] = tuple(prod)
    write_file(PRODUCT_FILE, PRODUCT_STRUCT, products)

    log_action(f"StockIn id={import_id} product_id={pid} qty={qty}")
    print(
        f"Stock-In saved successfully (Import ID: {import_id}), "
        f"new stock qty = {prod[PROD_QTY]}"
    )


def menu_add():
    while True:
        print("\n==========================================")
        print("  1) Add ")
        print("==========================================")
        print("1. Add Product (เพิ่มสินค้า)")
        print("2. Add Category (เพิ่มหมวดหมู่สินค้า)")
        print("3. Add Stock-In (บันทึกรายการนำเข้าคลัง)")
        print("0. Back to Main Menu")
        choice = input("Select sub-menu [0-3]: ").strip()

        if choice == "1":
            add_product()
        elif choice == "2":
            add_category()
        elif choice == "3":
            add_stockin()
        elif choice == "0":
            break
        else:
            print("Invalid option.")


# --- Update ---

def update_product():
    print("\n --- Update Product ---")
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    pid = ask_int("Enter Product ID to update: ", label="Product ID")
    if pid is None:
        return

    i, p = find_by_id(products, PROD_ID, pid)
    if p is None or p[PROD_STATUS] == STATUS_DELETED:
        print("Product ID not found (or already deleted).")
        return

    curr_barcode = unpack_string(p[PROD_BARCODE])
    curr_name = unpack_string(p[PROD_NAME])
    curr_unit = unpack_string(p[PROD_UNIT])

    print("(Press Enter to keep current value)")
    barcode = ask_str(f"New Barcode [{curr_barcode}]: ", BARCODE_BYTES, True, "Barcode")
    if barcode is None:
        return
    name = ask_str(f"New Name [{curr_name}]: ", NAME_BYTES, True, "Product Name")
    if name is None:
        return
    cat_id = pick_active_category(
        f"New Category ID [{p[PROD_CAT]}]: ", allow_blank=True
    )
    if cat_id is None:
        return
    unit = ask_str(f"New Unit [{curr_unit}]: ", UNIT_BYTES, True, "Unit")
    if unit is None:
        return
    cost = ask_float(
        f"New Cost Price [{p[PROD_COST]:.2f}]: ", min_val=0,
        allow_blank=True, label="Cost Price",
    )
    if cost is None:
        return
    sell = ask_float(
        f"New Sell Price [{p[PROD_SELL]:.2f}]: ", min_val=0,
        allow_blank=True, label="Sell Price",
    )
    if sell is None:
        return
    qty = ask_int(
        f"New Stock Qty [{p[PROD_QTY]}]: ", min_val=0,
        allow_blank=True, label="Stock Qty",
    )
    if qty is None:
        return

    products[i] = (
        pid,
        pack_string(barcode or curr_barcode, BARCODE_BYTES),
        pack_string(name or curr_name, NAME_BYTES),
        p[PROD_CAT] if cat_id == "" else cat_id,
        pack_string(unit or curr_unit, UNIT_BYTES),
        p[PROD_COST] if cost == "" else cost,
        p[PROD_SELL] if sell == "" else sell,
        p[PROD_QTY] if qty == "" else qty,
        p[PROD_STATUS],
    )
    write_file(PRODUCT_FILE, PRODUCT_STRUCT, products)
    log_action(f"Update Product id={pid}")
    print("Product data updated successfully.")


def update_category():
    print("\n --- Update Category ---")
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    cid = ask_int("Enter Category ID to update: ", label="Category ID")
    if cid is None:
        return

    i, c = find_by_id(categories, CAT_ID, cid)
    if c is None or c[CAT_STATUS] == STATUS_DELETED:
        print("Category ID not found (or already deleted).")
        return

    curr_name = unpack_string(c[CAT_NAME])
    curr_desc = unpack_string(c[CAT_DESC])

    print("(Press Enter to keep current value)")
    name = ask_str(f"New Name [{curr_name}]: ", CAT_NAME_BYTES, True, "Category Name")
    if name is None:
        return
    desc = ask_str(f"New Description [{curr_desc}]: ", DESC_BYTES, True, "Description")
    if desc is None:
        return

    categories[i] = (
        cid,
        pack_string(name or curr_name, CAT_NAME_BYTES),
        pack_string(desc or curr_desc, DESC_BYTES),
        c[CAT_STATUS],
    )
    write_file(CATEGORY_FILE, CATEGORY_STRUCT, categories)
    log_action(f"Update Category id={cid}")
    print("Category data updated successfully.")


def menu_update():
    while True:
        print("\n==========================================")
        print("  2) Update ")
        print("==========================================")
        print("1. Update Product Data")
        print("2. Update Category Data")
        print("0. Back to Main Menu")
        print("(Stock-In ไม่รองรับการแก้ไข ให้บันทึกรายการใหม่แทน)")
        choice = input("Select sub-menu [0-2]: ").strip()

        if choice == "1":
            update_product()
        elif choice == "2":
            update_category()
        elif choice == "0":
            break
        else:
            print("Invalid option.")


# --- Delete ---

def delete_product():
    print("\n --- Delete Product (Soft Delete) ---")
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    pid = ask_int("Enter Product ID to delete: ", label="Product ID")
    if pid is None:
        return

    if soft_delete(PRODUCT_FILE, PRODUCT_STRUCT, products, PROD_ID, PROD_STATUS, pid):
        log_action(f"Delete Product id={pid}")
        print("Product deleted successfully (Status changed to Deleted).")
    else:
        print("Product ID not found or already deleted.")


def delete_category():
    print("\n --- Delete Category (Soft Delete) ---")
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    cid = ask_int("Enter Category ID to delete: ", label="Category ID")
    if cid is None:
        return

    if soft_delete(CATEGORY_FILE, CATEGORY_STRUCT, categories, CAT_ID, CAT_STATUS, cid):
        log_action(f"Delete Category id={cid}")
        print("Category deleted successfully (Status changed to Deleted).")
    else:
        print("Category ID not found or already deleted.")


def menu_delete():
    while True:
        print("\n==========================================")
        print("  3) Delete ")
        print("==========================================")
        print("1. Delete Product")
        print("2. Delete Category")
        print("0. Back to Main Menu")
        choice = input("Select sub-menu [0-2]: ").strip()

        if choice == "1":
            delete_product()
        elif choice == "2":
            delete_category()
        elif choice == "0":
            break
        else:
            print("Invalid option.")


# --- View & Search ---

def search_category_products():
    cid = ask_int("\nEnter Category ID: ", label="Category ID")
    if cid is None:
        return

    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)

    _, cat = find_by_id(categories, CAT_ID, cid)
    if not cat:
        print("Category ID not found.")
        return

    print(
        f"\n--- Products in Category: {unpack_string(cat[CAT_NAME])} "
        f"(ID: {cid}, {status_text(cat[CAT_STATUS])}) ---"
    )
    items = [p for p in products if p[PROD_CAT] == cid]
    if not items:
        print("No products in this category.")
        return

    print_table(PRODUCT_HEADERS, PRODUCT_W, [product_row(p, categories) for p in items])

    actives = [p for p in items if p[PROD_STATUS] == STATUS_ACTIVE]
    total_qty = sum(p[PROD_QTY] for p in actives)
    value_cost = sum(p[PROD_QTY] * p[PROD_COST] for p in actives)
    value_sell = sum(p[PROD_QTY] * p[PROD_SELL] for p in actives)
    print(f"Total Active Products : {len(actives)}")
    print(f"Total Stock Quantity  : {total_qty}")
    print(f"Stock Value (Cost)    : {value_cost:.2f} THB")
    print(f"Stock Value (Sell)    : {value_sell:.2f} THB")


def search_product_stockins():
    pid = ask_int("\nEnter Product ID: ", label="Product ID")
    if pid is None:
        return

    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)

    _, prod = find_by_id(products, PROD_ID, pid)
    if not prod:
        print("Product ID not found.")
        return

    print(
        f"\n--- Stock-In History: {unpack_string(prod[PROD_NAME])} (ID: {pid}) ---"
    )
    items = [s for s in stockins if s[SIN_PID] == pid]
    if not items:
        print("No stock-in records for this product.")
        return

    print_table(STOCKIN_HEADERS, STOCKIN_W, [stockin_row(s, products) for s in items])
    print(f"Total Entries           : {len(items)}")
    print(f"Total Quantity Received : {sum(s[SIN_QTY] for s in items)}")
    print(f"Total Cost              : {sum(s[SIN_TOTAL] for s in items):.2f} THB")
    print(f"Current Stock           : {prod[PROD_QTY]}")


def search_supplier_stockins():
    keyword = input("\nEnter Supplier Name: ").strip().lower()
    if not keyword:
        print("[Error] Supplier Name cannot be empty.")
        return

    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)

    matches = [s for s in stockins if keyword in unpack_string(s[SIN_SUPPLIER]).lower()]
    if not matches:
        print("No stock-in records found for this supplier.")
        return

    suppliers = {}
    for s in matches:
        suppliers.setdefault(unpack_string(s[SIN_SUPPLIER]), []).append(s)

    print("\n" + "=" * 80)
    print(f" Stock-In Records & Products from Supplier matching: '{keyword}'")
    print("=" * 80)

    grand_qty = 0
    grand_cost = 0.0
    for sup_name, items in suppliers.items():
        print(f"\nSupplier: {sup_name}")
        print_table(
            STOCKIN_HEADERS, STOCKIN_W, [stockin_row(s, products) for s in items]
        )
        sup_qty = sum(s[SIN_QTY] for s in items)
        sup_cost = sum(s[SIN_TOTAL] for s in items)
        grand_qty += sup_qty
        grand_cost += sup_cost
        print(f"  Entries: {len(items)} | Quantity: {sup_qty} | Cost: {sup_cost:.2f} THB")

    print("\n" + "-" * 80)
    print(f"Total Quantity Received: {grand_qty} | Total Cost: {grand_cost:.2f} THB")


def view_one_product():
    pid = ask_int("\nEnter Product ID: ", label="Product ID")
    if pid is None:
        return
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    _, p = find_by_id(products, PROD_ID, pid)
    if p is None:
        print("Product ID not found.")
        return
    print_table(PRODUCT_HEADERS, PRODUCT_W, [product_row(p, categories)])


def view_filtered_products():
    print("\n--- Filter Products ---")
    print("1. Filter by Category (กรองตามหมวดหมู่)")
    print("2. Low Stock (สินค้าใกล้หมด: คงเหลือ <= ที่กำหนด)")
    print("3. Active Products Only (เฉพาะสินค้าที่ Active)")
    choice = input("Select [1-3]: ").strip()

    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)

    if choice == "1":
        cat_id = ask_int("Category ID: ", label="Category ID")
        if cat_id is None:
            return
        rows = [p for p in products if p[PROD_CAT] == cat_id]
    elif choice == "2":
        threshold = ask_int("Stock threshold: ", min_val=0, label="Threshold")
        if threshold is None:
            return
        rows = [p for p in products if p[PROD_QTY] <= threshold]
    elif choice == "3":
        rows = [p for p in products if p[PROD_STATUS] == STATUS_ACTIVE]
    else:
        print("Invalid option.")
        return

    if not rows:
        print("No products match the condition.")
        return
    print_table(PRODUCT_HEADERS, PRODUCT_W, [product_row(p, categories) for p in rows])


def view_product_summary():
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stats = calc_product_stats(products)

    print("\n--- Product Statistics (สถิติโดยสรุป) ---")
    print(f"  Total Products (records) : {stats['total']}")
    print(f"  Active                   : {stats['active']}")
    print(f"  Deleted                  : {stats['deleted']}")
    if stats["active"]:
        print(f"  Total Stock Quantity     : {stats['total_qty']}")
        print(f"  Low Stock (<={LOW_STOCK_LIMIT})          : {len(stats['low_stock'])}")
        print(f"  Average Sell Price       : {stats['avg_sell']:.2f} THB")


def view_all():
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)

    print("\n================ All Categories ================")
    if not categories:
        print("No category records found.")
    else:
        print_table(CATEGORY_HEADERS, CATEGORY_W, [category_row(c) for c in categories])

    print("\n================ All Products ================")
    if not products:
        print("No product records found.")
    else:
        print_table(
            PRODUCT_HEADERS, PRODUCT_W, [product_row(p, categories) for p in products]
        )

    print("\n================ All Stock-In Records ================")
    if not stockins:
        print("No stock-in records found.")
    else:
        print_table(
            STOCKIN_HEADERS, STOCKIN_W, [stockin_row(s, products) for s in stockins]
        )


def menu_view():
    while True:
        print("\n==========================================")
        print("  4) View & Search ")
        print("==========================================")
        print("1. Search Products by Category ID (ค้นหาสินค้าตามหมวดหมู่ + รวมมูลค่าสต็อก)")
        print("2. Search Stock-In by Product ID (ค้นหารายการนำเข้าตามรหัสสินค้า)")
        print("3. Search Stock-In & Products by Supplier (ค้นหาตามชื่อผู้จำหน่าย)")
        print("4. View One Product (ดูสินค้ารายการเดียว)")
        print("5. Filter Products (ดูสินค้าแบบกรอง)")
        print("6. Product Statistics (สถิติโดยสรุป)")
        print("7. View All Records (แสดงข้อมูลทั้งหมด)")
        print("0. Back to Main Menu")
        choice = input("Select sub-menu [0-7]: ").strip()

        if choice == "1":
            search_category_products()
        elif choice == "2":
            search_product_stockins()
        elif choice == "3":
            search_supplier_stockins()
        elif choice == "4":
            view_one_product()
        elif choice == "5":
            view_filtered_products()
        elif choice == "6":
            view_product_summary()
        elif choice == "7":
            view_all()
        elif choice == "0":
            break
        else:
            print("Invalid option.")


# --- Generate Report ---

def publish_report(filename, open_after=True):
    """คัดลอกรายงานไปที่ Desktop และเปิดไฟล์ (ถ้าทำได้)"""
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        desktop_file = os.path.join(desktop, filename)
        shutil.copyfile(filename, desktop_file)

        if not open_after:
            return
        if os.name == "nt":
            subprocess.Popen(["notepad.exe", desktop_file])
        elif os.name == "posix":
            opener = "open" if "DARWIN" in os.uname().sysname.upper() else "xdg-open"
            subprocess.Popen([opener, desktop_file])
    except Exception:
        pass


# ============================================================
# Compact table + compact reports (สั้นลงแต่ข้อมูลครบเท่าเดิม)
# ============================================================

REPORT_W = 90


def render_compact(headers, rows, aligns=None):
    """ตารางสำหรับรายงาน .txt ที่เส้นไม่เหลื่อมใน Notepad
    - คอลัมน์ที่ไม่ใช่คอลัมน์สุดท้ายต้องเป็นตัวเลข/อังกฤษ จัดความกว้างตามข้อมูลจริง
    - คอลัมน์สุดท้าย (ข้อความไทยได้) ไม่เติมช่องว่างและไม่มีเส้นปิดขวา
      เพราะ Notepad วาดตัวอักษรไทยกว้างไม่เท่ากัน การเติมช่องว่างจะทำให้เส้นเพี้ยน
    - ข้อความไม่ถูกตัด ข้อมูลทุกช่องแสดงครบ"""
    n = len(headers)
    aligns = aligns or ["l"] * n
    cells = [[clean_thai_str(c) for c in r] for r in rows]
    heads = [clean_thai_str(h) for h in headers]
    widths = [
        max([display_width(heads[i])] + [display_width(r[i]) for r in cells])
        for i in range(n)
    ]

    def line(vals):
        parts = [
            pad_str(vals[i], widths[i], "right" if aligns[i] == "r" else "left")
            for i in range(n - 1)
        ]
        parts.append(vals[n - 1])           # คอลัมน์สุดท้าย: ไม่เติมช่องว่าง
        return "| " + " | ".join(parts)     # ไม่มี " |" ปิดท้าย

    border = (
        "+" + "".join("-" * (wd + 2) + "+" for wd in widths[:-1])
        + "-" * (widths[-1] + 2)
    )
    return [border, line(heads), border] + [line(r) for r in cells] + [border]


def _banner(title, now_str, extra=()):
    lines = ["=" * REPORT_W, title.center(REPORT_W), "=" * REPORT_W,
             f"Generated At : {now_str}  |  App Version : {APP_VERSION}"]
    lines += list(extra)
    lines += ["Storage      : Binary fixed-length, Little-Endian, UTF-8", "=" * REPORT_W]
    return lines


def _write_lines(filename, lines):
    def is_rule(l):
        return len(l) == REPORT_W and l and set(l) in ({"="}, {"-"})

    width = max(
        [REPORT_W] + [display_width(l.rstrip()) for l in lines if not is_rule(l)]
    )
    out = []
    for i, l in enumerate(lines):
        if is_rule(l):
            l = l[0] * width
        elif i == 1:                      # บรรทัดชื่อรายงาน จัดกึ่งกลางใหม่
            l = l.strip().center(width)
        out.append(l)
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


R_PROD_H = ["ID", "Barcode", "Cost", "Sell", "Qty", "Status", "Cat", "Name [Unit]"]
R_PROD_A = ["l", "l", "r", "r", "r", "l", "r", "l"]
R_CAT_H = ["ID", "Status", "Name - Description"]
R_SIN_H = ["ImpID", "ProdID", "Qty", "Cost/Unit", "Total", "Date", "Supplier"]
R_SIN_A = ["l", "l", "r", "r", "r", "l", "l"]


def _prod_rows(products):
    return [[p[PROD_ID], unpack_string(p[PROD_BARCODE]), f"{p[PROD_COST]:.2f}",
             f"{p[PROD_SELL]:.2f}", p[PROD_QTY], status_text(p[PROD_STATUS]), p[PROD_CAT],
             f"{unpack_string(p[PROD_NAME])} [{unpack_string(p[PROD_UNIT])}]"] for p in products]


def _sin_rows(stockins):
    return [[s[SIN_ID], s[SIN_PID], s[SIN_QTY], f"{s[SIN_COST]:.2f}", f"{s[SIN_TOTAL]:.2f}",
             fmt_ts(s[SIN_DATE]), unpack_string(s[SIN_SUPPLIER])] for s in stockins]


def generate_report(open_after=True):
    """รายงานการนำเข้าคลัง (Stock-In) เท่านั้น -> stockin_report.txt"""
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    W = REPORT_W

    L = _banner("STOCK-IN REPORT", now_str,
                [f"Records      : {len(stockins)} stock-in entries"])

    L += ["", f"ALL STOCK-IN RECORDS ({len(stockins)})"]
    if stockins:
        L += render_compact(R_SIN_H, _sin_rows(stockins), R_SIN_A)
    else:
        L.append("  (No stock-in records)")

    L += ["", "=" * W, "STOCK-IN SUMMARY", "-" * W]
    L += render_compact(["Item", "Detail"], [[
        "Stock-In",
        f"{len(stockins)} entries | {sum(s[SIN_QTY] for s in stockins)} units received | "
        f"{sum(s[SIN_TOTAL] for s in stockins):.2f} THB"]])

    sup = {}
    for s in stockins:
        t = sup.setdefault(unpack_string(s[SIN_SUPPLIER]) or "Unknown", [0, 0, 0.0])
        t[0] += 1
        t[1] += s[SIN_QTY]
        t[2] += s[SIN_TOTAL]
    if sup:
        L += ["", "Stock-in by supplier:"]
        L += render_compact(
            ["Entries", "Units", "Cost (THB)", "Supplier"],
            [[n, q, f"{c:.2f}", name] for name, (n, q, c) in sup.items()],
            ["r", "r", "r", "l"])
    L.append("=" * W)
    _write_lines(REPORT_FILE, L)
    publish_report(REPORT_FILE, open_after)
    print(f"\n[Success] Stock-In Report generated successfully: {REPORT_FILE}")


def generate_category_report():
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    L = _banner("CATEGORY PRODUCT & STOCK REPORT", now_str,
                [f"Records      : {len(categories)} categories, {len(products)} products"])
    g_items = g_active = g_qty = 0
    g_cost = g_sell = 0.0
    for c in categories:
        cid = c[CAT_ID]
        desc = unpack_string(c[CAT_DESC])
        items = [p for p in products if p[PROD_CAT] == cid]
        actives = [p for p in items if p[PROD_STATUS] == STATUS_ACTIVE]
        qty = sum(p[PROD_QTY] for p in actives)
        vc = sum(p[PROD_QTY] * p[PROD_COST] for p in actives)
        vs = sum(p[PROD_QTY] * p[PROD_SELL] for p in actives)
        g_items += len(items); g_active += len(actives); g_qty += qty
        g_cost += vc; g_sell += vs

        L += ["", f"CATEGORY {cid} ({status_text(c[CAT_STATUS])}) : "
                  f"{unpack_string(c[CAT_NAME])}" + (f" - {desc}" if desc else "")]
        if items:
            rows = _prod_rows(items)
            rows = [[i] + r for i, r in enumerate(rows, 1)]
            L += render_compact(["No."] + R_PROD_H, rows, ["r"] + R_PROD_A)
        else:
            L.append("  (No products in this category)")
        L.append(f"  >> {len(items)} item(s) (Active {len(actives)}) | Stock Qty {qty} | "
                 f"Value Cost {vc:.2f} / Sell {vs:.2f} THB")

    act_cat = sum(1 for c in categories if c[CAT_STATUS] == STATUS_ACTIVE)
    L += ["", "=" * REPORT_W, "OVERALL SUMMARY", "-" * REPORT_W]
    L += render_compact(["Item", "Detail"], [
        ["Categories", f"{len(categories)} (Active {act_cat}, Deleted {len(categories) - act_cat})"],
        ["Products", f"{g_items} (Active {g_active}) | Stock Qty {g_qty}"],
        ["Stock Value", f"Cost {g_cost:.2f} THB | Sell {g_sell:.2f} THB"],
    ])
    L.append("=" * REPORT_W)
    _write_lines(CATEGORY_REPORT_FILE, L)
    publish_report(CATEGORY_REPORT_FILE)
    print(f"[Success] Category Report generated successfully: {CATEGORY_REPORT_FILE}")


def generate_product_report():
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    print("\n--- Generate Product Individual Report ---")
    search_id = ask_int("Enter Product ID: ", label="Product ID")
    if search_id is None:
        return
    _, product = find_by_id(products, PROD_ID, search_id)
    if not product:
        print(f"[Error] Product ID '{search_id}' not found.")
        return
    p_ins = [s for s in stockins if s[SIN_PID] == search_id]

    L = _banner("INDIVIDUAL PRODUCT STOCK REPORT", now_str)
    L += ["", "PRODUCT"]
    L += render_compact(R_PROD_H, _prod_rows([product]), R_PROD_A)
    L += ["", "STOCK-IN HISTORY"]
    if p_ins:
        # ตัดคอลัมน์ ProdID ออก เพราะเป็นสินค้าตัวเดียวกันทั้งหมด
        sin_h = [h for h in R_SIN_H if h != "ProdID"]
        sin_a = [a for h, a in zip(R_SIN_H, R_SIN_A) if h != "ProdID"]
        rows = [[i, r[0]] + r[2:] for i, r in enumerate(_sin_rows(p_ins), 1)]
        L += render_compact(["No."] + sin_h, rows, ["r"] + sin_a)
    else:
        L.append("  (No stock-in record found)")
    L.append("=" * REPORT_W)
    _write_lines(PRODUCT_REPORT_FILE, L)
    publish_report(PRODUCT_REPORT_FILE)
    print(f"\n[Success] Individual Product Report generated successfully: {PRODUCT_REPORT_FILE}")



# --- Main Menu ---

def safe_exit():
    print("\nClosing the program safely...")
    generate_report(open_after=False)
    print("Data saved and files closed. Goodbye!")


def main():
    upgrade_all_data_files()
    while True:
        print("\n==========================================")
        print("  Grocery Stock System (ระบบสต็อกสินค้าร้านขายของชำ)")
        print("==========================================")
        print("1) Add ")
        print("2) Update ")
        print("3) Delete ")
        print("4) View & Search ")
        print("5) Generate Stock-In Report (รายงานสินค้าเข้าคลัง)")
        print("6) Generate Category Report (รายงานแยกตามหมวดหมู่)")
        print("7) Generate Product Report (รายงานรายสินค้า)")
        print("0) Exit")
        choice = input("Select option [0-7]: ").strip()
        if choice == "1":
            menu_add()
        elif choice == "2":
            menu_update()
        elif choice == "3":
            menu_delete()
        elif choice == "4":
            menu_view()
        elif choice == "5":
            generate_report()
        elif choice == "6":
            generate_category_report()
        elif choice == "7":
            generate_product_report()
        elif choice == "0":
            safe_exit()
            break
        else:
            print("Invalid option. Please select [0-7].")


if __name__ == "__main__":
    main()