from datetime import datetime
import os
import shutil
import struct
import subprocess
from typing import List, Tuple
import unicodedata

APP_VERSION = "1.0"

# ไฟล์ข้อมูล (ใช้ชื่อและรูปแบบเดียวกับ grocery_stock.py เดิม อ่านไฟล์เก่าได้ทันที)
PRODUCT_FILE = "product.dat"
CATEGORY_FILE = "category.dat"
STOCKIN_FILE = "stockin.dat"

# product : id, barcode, name, category_id, unit, cost, sell, qty, status
PRODUCT_STRUCT = struct.Struct("<i15s50si10sffii")
# category: id, name, description, status
CATEGORY_STRUCT = struct.Struct("<i30s50si")
# stockin : import_id, product_id, quantity, cost, total_cost, supplier, import_date
STOCKIN_STRUCT = struct.Struct("<iiiff30si")

REPORT_FILE = "report.txt"
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
        print(f"[Error] {label} is too long (max {max_bytes} bytes).")
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

    name = ask_str("Category Name: ", 30, label="Category Name")
    if name is None:
        return
    desc = ask_str("Description (optional): ", 50, allow_blank=True, label="Description")
    if desc is None:
        return

    cid = next_id(categories, CAT_ID, 1)
    record = (cid, pack_string(name, 30), pack_string(desc, 50), STATUS_ACTIVE)
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

    barcode = ask_str("Barcode: ", 15, label="Barcode")
    if barcode is None:
        return
    name = ask_str("Product Name: ", 50, label="Product Name")
    if name is None:
        return
    cat_id = pick_active_category()
    if cat_id is None:
        return
    unit = ask_str("Unit (เช่น ชิ้น, ขวด, กก.): ", 10, label="Unit")
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
        pack_string(barcode, 15),
        pack_string(name, 50),
        cat_id,
        pack_string(unit, 10),
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
    supplier = ask_str("Supplier: ", 30, label="Supplier")
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
        pack_string(supplier, 30),
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
    barcode = ask_str(f"New Barcode [{curr_barcode}]: ", 15, True, "Barcode")
    if barcode is None:
        return
    name = ask_str(f"New Name [{curr_name}]: ", 50, True, "Product Name")
    if name is None:
        return
    cat_id = pick_active_category(
        f"New Category ID [{p[PROD_CAT]}]: ", allow_blank=True
    )
    if cat_id is None:
        return
    unit = ask_str(f"New Unit [{curr_unit}]: ", 10, True, "Unit")
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
        pack_string(barcode or curr_barcode, 15),
        pack_string(name or curr_name, 50),
        p[PROD_CAT] if cat_id == "" else cat_id,
        pack_string(unit or curr_unit, 10),
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
    name = ask_str(f"New Name [{curr_name}]: ", 30, True, "Category Name")
    if name is None:
        return
    desc = ask_str(f"New Description [{curr_desc}]: ", 50, True, "Description")
    if desc is None:
        return

    categories[i] = (
        cid,
        pack_string(name or curr_name, 30),
        pack_string(desc or curr_desc, 50),
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


def generate_report(open_after=True):
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    stockins = read_file(STOCKIN_FILE, STOCKIN_STRUCT)
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    LINE_WIDTH = sum(PRODUCT_W) + (len(PRODUCT_W) * 3) + 1

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * LINE_WIDTH + "\n")
        f.write("GROCERY STOCK SYSTEM - SUMMARY REPORT".center(LINE_WIDTH) + "\n")
        f.write("=" * LINE_WIDTH + "\n")
        f.write(f" Generated At : {now_str}\n")
        f.write(f" App Version  : {APP_VERSION}\n")
        f.write(" Endianness   : Little-Endian\n")
        f.write(" Encoding     : UTF-8 (fixed-length)\n")
        f.write("=" * LINE_WIDTH + "\n\n")

        f.write("ALL PRODUCTS\n")
        for line in render_table(
            PRODUCT_HEADERS, PRODUCT_W, [product_row(p) for p in products]
        ):
            f.write(line + "\n")
        f.write("\n")

        f.write("ALL CATEGORIES\n")
        for line in render_table(
            CATEGORY_HEADERS, CATEGORY_W, [category_row(c) for c in categories]
        ):
            f.write(line + "\n")
        f.write("\n")

        f.write("ALL STOCK-IN RECORDS\n")
        for line in render_table(
            STOCKIN_HEADERS, STOCKIN_W, [stockin_row(s) for s in stockins]
        ):
            f.write(line + "\n")

        # --- Summary (Products) ---
        stats = calc_product_stats(products)
        f.write("\n\n" + "=" * LINE_WIDTH + "\n")
        f.write("SYSTEM STATISTICAL SUMMARY\n")
        f.write("-" * LINE_WIDTH + "\n")
        f.write(f"  * Total Products (records) : {stats['total']}\n")
        f.write(f"    - Active Products        : {stats['active']}\n")
        f.write(f"    - Deleted Products       : {stats['deleted']}\n")
        if stats["active"]:
            f.write(f"  * Total Stock Quantity     : {stats['total_qty']}\n")
            f.write(f"  * Low Stock (<={LOW_STOCK_LIMIT}) count    : {len(stats['low_stock'])}\n")
            f.write(f"  * Average Sell Price       : {stats['avg_sell']:.2f}\n")
        f.write("-" * LINE_WIDTH + "\n\n")

        if stats["low_stock"]:
            f.write(f"LOW STOCK PRODUCTS (<= {LOW_STOCK_LIMIT})\n")
            f.write("-" * LINE_WIDTH + "\n")
            for p in stats["low_stock"]:
                f.write(
                    f"  * Qty {p[PROD_QTY]:>5} | ID {p[PROD_ID]} | "
                    f"{unpack_string(p[PROD_NAME])} [{unpack_string(p[PROD_UNIT])}]\n"
                )
            f.write("-" * LINE_WIDTH + "\n\n")

        # --- Categories ---
        f.write("PRODUCTS BY CATEGORY (Active products)\n")
        f.write("-" * LINE_WIDTH + "\n")
        f.write(f"  * Total Categories : {len(categories)}\n")
        for c in categories:
            cnt = sum(
                1 for p in products
                if p[PROD_CAT] == c[CAT_ID] and p[PROD_STATUS] == STATUS_ACTIVE
            )
            f.write(
                f"    [{c[CAT_ID]:>3}] {status_text(c[CAT_STATUS]):<8} | "
                f"{cnt:>4} product(s) | {unpack_string(c[CAT_NAME])}\n"
            )
        f.write("-" * LINE_WIDTH + "\n\n")

        # --- Stock-In ---
        f.write("STOCK-IN RECORDS\n")
        f.write("-" * LINE_WIDTH + "\n")
        f.write(f"  * Total Stock-In Entries  : {len(stockins)}\n")
        if stockins:
            f.write(f"  * Total Quantity Received : {sum(s[SIN_QTY] for s in stockins)}\n")
            f.write(
                f"  * Total Cost of Goods In  : {sum(s[SIN_TOTAL] for s in stockins):.2f} THB\n"
            )
        f.write("-" * LINE_WIDTH + "\n\n")

        supplier_totals = {}
        for s in stockins:
            sup = unpack_string(s[SIN_SUPPLIER]) or "Unknown"
            t = supplier_totals.setdefault(sup, [0, 0, 0.0])
            t[0] += 1
            t[1] += s[SIN_QTY]
            t[2] += s[SIN_TOTAL]

        f.write("STOCK-IN BY SUPPLIER\n")
        f.write("-" * LINE_WIDTH + "\n")
        for sup, (n, q, c) in supplier_totals.items():
            f.write(f"  * {n:>4} entry(ies) | {q:>7} unit(s) | {c:>12.2f} THB | {sup}\n")
        f.write("-" * LINE_WIDTH + "\n\n")

        # --- Activity log ---
        f.write("RECENT ACTIVITY LOG (this session)\n")
        f.write("-" * LINE_WIDTH + "\n")
        if action_log:
            for entry in action_log[-20:]:
                f.write(f"  {entry}\n")
        else:
            f.write("  (no actions this session)\n")
        f.write("=" * LINE_WIDTH + "\n")

    publish_report(REPORT_FILE, open_after)
    print(f"\n[Success] Report generated successfully: {REPORT_FILE}")


CATEGORY_REPORT_HEADERS = [
    "No.", "Product ID", "Barcode", "Cost", "Sell", "Qty", "Status", "Name [Unit]",
]
CATEGORY_REPORT_W = [6, 10, 15, 9, 9, 7, 8, 40]


def generate_category_report():
    categories = read_file(CATEGORY_FILE, CATEGORY_STRUCT)
    products = read_file(PRODUCT_FILE, PRODUCT_STRUCT)
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    w = CATEGORY_REPORT_W
    LINE_WIDTH = sum(w) + (len(w) * 3) + 1

    with open(CATEGORY_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * LINE_WIDTH + "\n")
        f.write("CATEGORY PRODUCT & STOCK REPORT".center(LINE_WIDTH) + "\n")
        f.write("=" * LINE_WIDTH + "\n")
        f.write(f" Generated At     : {now_str}\n")
        f.write(f" Total Categories : {len(categories)}\n")
        f.write("=" * LINE_WIDTH + "\n\n\n")

        for c in categories:
            cid = c[CAT_ID]
            f.write(" " + "=" * (LINE_WIDTH - 2) + "\n")
            f.write(f"  CATEGORY ID : {cid}  ({status_text(c[CAT_STATUS])})\n")
            f.write(f"  Name        : {unpack_string(c[CAT_NAME])}\n")
            f.write(f"  Description : {unpack_string(c[CAT_DESC])}\n")
            f.write(" " + "=" * (LINE_WIDTH - 2) + "\n\n")

            items = [p for p in products if p[PROD_CAT] == cid]
            if not items:
                f.write("    (No products in this category)\n\n")
            else:
                rows = []
                for idx, p in enumerate(items, 1):
                    rows.append([
                        idx,
                        p[PROD_ID],
                        unpack_string(p[PROD_BARCODE]),
                        f"{p[PROD_COST]:.2f}",
                        f"{p[PROD_SELL]:.2f}",
                        p[PROD_QTY],
                        status_text(p[PROD_STATUS]),
                        f"{unpack_string(p[PROD_NAME])} [{unpack_string(p[PROD_UNIT])}]",
                    ])
                for line in render_table(CATEGORY_REPORT_HEADERS, w, rows):
                    f.write(line + "\n")
                f.write("\n")

            actives = [p for p in items if p[PROD_STATUS] == STATUS_ACTIVE]
            total_qty = sum(p[PROD_QTY] for p in actives)
            value_cost = sum(p[PROD_QTY] * p[PROD_COST] for p in actives)
            value_sell = sum(p[PROD_QTY] * p[PROD_SELL] for p in actives)

            f.write("  " + "-" * (LINE_WIDTH - 4) + "\n")
            f.write(f"  >> SUMMARY FOR CATEGORY ID {cid}\n")
            f.write(f"     * Total Products (all)    : {len(items)} Item(s)\n")
            f.write(f"     * Active Products         : {len(actives)} Item(s)\n")
            f.write(f"     * Total Stock Quantity    : {total_qty}\n")
            f.write(f"     * Stock Value (Cost)      : {value_cost:.2f} THB\n")
            f.write(f"     * Stock Value (Sell)      : {value_sell:.2f} THB\n")
            f.write("  " + "-" * (LINE_WIDTH - 4) + "\n\n\n")

    publish_report(CATEGORY_REPORT_FILE)
    print(f"[Success] Category Report generated successfully: {CATEGORY_REPORT_FILE}")


PRODUCT_REPORT_HEADERS = [
    "No.", "Import ID", "Quantity", "Cost/Unit", "Total Cost", "Import Date", "Supplier",
]
PRODUCT_REPORT_W = [6, 10, 10, 11, 12, 16, 30]


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

    w = PRODUCT_REPORT_W
    LINE_WIDTH = sum(w) + (len(w) * 3) + 1

    with open(PRODUCT_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * LINE_WIDTH + "\n")
        f.write("INDIVIDUAL PRODUCT STOCK REPORT".center(LINE_WIDTH) + "\n")
        f.write("=" * LINE_WIDTH + "\n")
        f.write(f" Generated At : {now_str}\n")
        f.write("=" * LINE_WIDTH + "\n\n")

        f.write("PRODUCT INFORMATION\n")
        f.write("-" * LINE_WIDTH + "\n")
        f.write(f"  Product ID  : {product[PROD_ID]}\n")
        f.write(f"  Barcode     : {unpack_string(product[PROD_BARCODE])}\n")
        f.write(f"  Cost Price  : {product[PROD_COST]:.2f}\n")
        f.write(f"  Sell Price  : {product[PROD_SELL]:.2f}\n")
        f.write(f"  Stock Qty   : {product[PROD_QTY]}\n")
        f.write(f"  Status      : {status_text(product[PROD_STATUS])}\n")
        f.write(f"  Name        : {unpack_string(product[PROD_NAME])}\n")
        f.write(f"  Unit        : {unpack_string(product[PROD_UNIT])}\n")
        f.write(f"  Category    : {category_label(categories, product[PROD_CAT])}\n")
        f.write("-" * LINE_WIDTH + "\n\n")

        f.write("STOCK-IN HISTORY\n")
        total_qty = 0
        total_cost = 0.0
        rows = []
        for idx, s in enumerate(p_ins, 1):
            total_qty += s[SIN_QTY]
            total_cost += s[SIN_TOTAL]
            rows.append([
                idx,
                s[SIN_ID],
                s[SIN_QTY],
                f"{s[SIN_COST]:.2f}",
                f"{s[SIN_TOTAL]:.2f}",
                fmt_ts(s[SIN_DATE]),
                unpack_string(s[SIN_SUPPLIER]),
            ])
        if not rows:
            rows.append(["-", "-", "-", "-", "-", "-", "No stock-in record found"])
        for line in render_table(PRODUCT_REPORT_HEADERS, w, rows):
            f.write(line + "\n")
        f.write("\n")

        f.write("SUMMARY\n")
        f.write("-" * LINE_WIDTH + "\n")
        f.write(f"  * Total Stock-In Entries  : {len(p_ins)} Record(s)\n")
        f.write(f"  * Total Quantity Received : {total_qty}\n")
        f.write(f"  * Total Cost of Goods In  : {total_cost:.2f} THB\n")
        f.write(f"  * Current Stock           : {product[PROD_QTY]}\n")
        f.write("=" * LINE_WIDTH + "\n")

    publish_report(PRODUCT_REPORT_FILE)
    print(f"\n[Success] Individual Product Report generated successfully: {PRODUCT_REPORT_FILE}")


# --- Main Menu ---

def safe_exit():
    print("\nClosing the program safely...")
    generate_report(open_after=False)
    print("Data saved and files closed. Goodbye!")


def main():
    while True:
        print("\n==========================================")
        print("  Grocery Stock System (ระบบสต็อกสินค้าร้านขายของชำ)")
        print("==========================================")
        print("1) Add ")
        print("2) Update ")
        print("3) Delete ")
        print("4) View & Search ")
        print("5) Generate Summary Report (รายงานสรุปทั้งระบบ)")
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