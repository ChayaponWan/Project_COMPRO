#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ระบบสต็อกสินค้าร้านขายของชำ (Grocery Store Stock Management System)
=====================================================================
เก็บข้อมูลลงไฟล์ไบนารีด้วยโมดูล struct (fixed-length records, little-endian)

ไฟล์ที่ใช้:
  - product.dat   : ข้อมูลสินค้า
  - category.dat  : ข้อมูลหมวดหมู่สินค้า
  - stockin.dat   : รายการนำเข้าสินค้าเข้าคลัง
  - report.txt    : รายงานสรุป (text report)

Requirements: Python 3.10+ / Standard Library only (struct, os, datetime, textwrap)
"""

import struct
import os
import datetime
import textwrap

# ============================================================
# 1) FILE / RECORD SPECIFICATIONS
# ============================================================

APP_VERSION = "1.0"
ENDIAN = "<"  # little-endian

PRODUCT_FILE = "product.dat"
CATEGORY_FILE = "category.dat"
STOCKIN_FILE = "stockin.dat"
REPORT_FILE = "report.txt"

# --- Product record: id, barcode, name, category_id, unit, cost, sell, qty, status
PRODUCT_FMT = ENDIAN + "i15s50si10sffii"
PRODUCT_SIZE = struct.calcsize(PRODUCT_FMT)
PRODUCT_FIELDS = ["product_id", "barcode", "name", "category_id", "unit",
                  "cost_price", "sell_price", "stock_qty", "status"]

# --- Category record: id, name, description, status
CATEGORY_FMT = ENDIAN + "i30s50si"
CATEGORY_SIZE = struct.calcsize(CATEGORY_FMT)
CATEGORY_FIELDS = ["category_id", "category_name", "description", "status"]

# --- StockIn record: import_id, product_id, quantity, cost_price, total_cost, supplier, import_date
STOCKIN_FMT = ENDIAN + "iiiff30si"
STOCKIN_SIZE = struct.calcsize(STOCKIN_FMT)
STOCKIN_FIELDS = ["import_id", "product_id", "quantity", "cost_price",
                  "total_cost", "supplier", "import_date"]

STATUS_ACTIVE = 1
STATUS_DELETED = 0


# ============================================================
# 2) LOW-LEVEL HELPERS: STRING <-> FIXED-LENGTH BYTES
# ============================================================

def str_to_bytes(s: str, size: int) -> bytes:
    """Encode a string as UTF-8 and pad/truncate to `size` bytes."""
    b = s.encode("utf-8")[:size]
    return b.ljust(size, b"\x00")


def bytes_to_str(b: bytes) -> str:
    """Decode fixed-length bytes back to a string, stripping null padding."""
    return b.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def now_ts() -> int:
    return int(datetime.datetime.now().timestamp())


def fmt_ts(ts: int) -> str:
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except (OSError, OverflowError, ValueError):
        return "-"


# ============================================================
# 3) GENERIC BINARY TABLE HANDLER
# ============================================================

class Table:
    """
    Generic fixed-length binary record table.
    Handles Add / Update / Delete(soft) / View / iterate for any of the
    three files, given its filename, struct format, field names and
    which fields are strings (need str_to_bytes/bytes_to_str).
    """

    def __init__(self, filename, fmt, fields, str_fields, id_field, has_status=True):
        self.filename = filename
        self.fmt = fmt
        self.size = struct.calcsize(fmt)
        self.fields = fields
        self.str_fields = str_fields          # {field_name: byte_size}
        self.id_field = id_field
        self.has_status = has_status
        if not os.path.exists(self.filename):
            open(self.filename, "wb").close()

    # ---- pack / unpack ----
    def _pack(self, record: dict) -> bytes:
        values = []
        for f in self.fields:
            v = record[f]
            if f in self.str_fields:
                values.append(str_to_bytes(str(v), self.str_fields[f]))
            else:
                values.append(v)
        return struct.pack(self.fmt, *values)

    def _unpack(self, raw: bytes) -> dict:
        values = struct.unpack(self.fmt, raw)
        record = {}
        for f, v in zip(self.fields, values):
            if f in self.str_fields:
                record[f] = bytes_to_str(v)
            else:
                record[f] = v
        return record

    # ---- low-level I/O ----
    def count_records(self) -> int:
        return os.path.getsize(self.filename) // self.size

    def read_at(self, index: int) -> dict:
        with open(self.filename, "rb") as f:
            f.seek(index * self.size)
            raw = f.read(self.size)
        return self._unpack(raw)

    def write_at(self, index: int, record: dict):
        with open(self.filename, "r+b") as f:
            f.seek(index * self.size)
            f.write(self._pack(record))
            f.flush()
            os.fsync(f.fileno())

    def append(self, record: dict):
        with open(self.filename, "ab") as f:
            f.write(self._pack(record))
            f.flush()
            os.fsync(f.fileno())

    def all_records(self, include_deleted=True):
        """Yield (index, record) for every record in the file."""
        n = self.count_records()
        for i in range(n):
            rec = self.read_at(i)
            if not include_deleted and self.has_status and rec.get("status") == STATUS_DELETED:
                continue
            yield i, rec

    def find_index_by_id(self, id_value):
        for i, rec in self.all_records(include_deleted=True):
            if rec[self.id_field] == id_value:
                return i, rec
        return None, None

    def next_id(self, start=1):
        """Simple auto-increment: max existing id + 1 (across active+deleted)."""
        max_id = start - 1
        for _, rec in self.all_records(include_deleted=True):
            if rec[self.id_field] > max_id:
                max_id = rec[self.id_field]
        return max_id + 1

    def soft_delete(self, id_value) -> bool:
        idx, rec = self.find_index_by_id(id_value)
        if idx is None or rec["status"] == STATUS_DELETED:
            return False
        rec["status"] = STATUS_DELETED
        self.write_at(idx, rec)
        return True


# ============================================================
# 4) TABLE INSTANCES
# ============================================================

product_table = Table(
    PRODUCT_FILE, PRODUCT_FMT, PRODUCT_FIELDS,
    str_fields={"barcode": 15, "name": 50, "unit": 10},
    id_field="product_id",
)

category_table = Table(
    CATEGORY_FILE, CATEGORY_FMT, CATEGORY_FIELDS,
    str_fields={"category_name": 30, "description": 50},
    id_field="category_id",
)

stockin_table = Table(
    STOCKIN_FILE, STOCKIN_FMT, STOCKIN_FIELDS,
    str_fields={"supplier": 30},
    id_field="import_id",
    has_status=False,
)

action_log = []  # in-memory log of actions this session, used in report.txt


def log_action(msg: str):
    action_log.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


# ============================================================
# 5) INPUT VALIDATION HELPERS
# ============================================================

def input_int(prompt, min_val=None, max_val=None, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            val = int(raw)
        except ValueError:
            print("  ! กรุณาใส่ตัวเลขจำนวนเต็มเท่านั้น")
            continue
        if min_val is not None and val < min_val:
            print(f"  ! ค่าต้องไม่น้อยกว่า {min_val}")
            continue
        if max_val is not None and val > max_val:
            print(f"  ! ค่าต้องไม่มากกว่า {max_val}")
            continue
        return val


def input_float(prompt, min_val=None, allow_blank=False):
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            val = float(raw)
        except ValueError:
            print("  ! กรุณาใส่ตัวเลข (float) เท่านั้น")
            continue
        if min_val is not None and val < min_val:
            print(f"  ! ค่าต้องไม่น้อยกว่า {min_val}")
            continue
        return val


def input_str(prompt, max_bytes, allow_blank=False, required=True):
    while True:
        raw = input(prompt).strip()
        if raw == "" and allow_blank:
            return None
        if raw == "" and required:
            print("  ! ห้ามเว้นว่าง")
            continue
        if len(raw.encode("utf-8")) > max_bytes:
            print(f"  ! ข้อความยาวเกินขนาดที่กำหนด ({max_bytes} bytes) กรุณาสั้นกว่านี้")
            continue
        return raw


# ============================================================
# 6) CATEGORY CRUD
# ============================================================

def category_add():
    print("\n-- เพิ่มหมวดหมู่สินค้า --")
    name = input_str("ชื่อหมวดหมู่: ", 30)
    desc = input_str("คำอธิบาย (เว้นว่างได้): ", 50, allow_blank=True) or ""
    cid = category_table.next_id(1)
    rec = {"category_id": cid, "category_name": name, "description": desc,
           "status": STATUS_ACTIVE}
    category_table.append(rec)
    log_action(f"Add Category id={cid} name='{name}'")
    print(f"  -> เพิ่มหมวดหมู่สำเร็จ (ID: {cid})")


def category_pick_active(prompt="รหัสหมวดหมู่: "):
    """Helper used by Product Add/Update to select a valid category."""
    actives = [r for _, r in category_table.all_records(include_deleted=False)]
    if not actives:
        print("  ! ยังไม่มีหมวดหมู่ในระบบ กรุณาเพิ่มหมวดหมู่ก่อน")
        return None
    print("  หมวดหมู่ที่มี:")
    for r in actives:
        print(f"    [{r['category_id']}] {r['category_name']}")
    while True:
        cid = input_int(prompt)
        if any(r["category_id"] == cid for r in actives):
            return cid
        print("  ! ไม่พบรหัสหมวดหมู่นี้ หรือถูกลบไปแล้ว")


def category_view_all():
    print("\n-- รายการหมวดหมู่ทั้งหมด --")
    rows = list(category_table.all_records(include_deleted=True))
    if not rows:
        print("  (ไม่มีข้อมูล)")
        return
    print(f"{'ID':<5}{'ชื่อ':<20}{'คำอธิบาย':<30}{'สถานะ':<10}")
    print("-" * 65)
    for _, r in rows:
        status = "Active" if r["status"] == STATUS_ACTIVE else "Deleted"
        print(f"{r['category_id']:<5}{r['category_name']:<20}{r['description']:<30}{status:<10}")


def category_update():
    print("\n-- แก้ไขหมวดหมู่ --")
    cid = input_int("รหัสหมวดหมู่ที่ต้องการแก้ไข: ")
    idx, rec = category_table.find_index_by_id(cid)
    if rec is None or rec["status"] == STATUS_DELETED:
        print("  ! ไม่พบหมวดหมู่นี้ (หรือถูกลบแล้ว)")
        return
    print(f"  ค่าปัจจุบัน: ชื่อ='{rec['category_name']}', คำอธิบาย='{rec['description']}'")
    name = input_str("ชื่อใหม่ (Enter=ไม่เปลี่ยน): ", 30, allow_blank=True)
    desc = input_str("คำอธิบายใหม่ (Enter=ไม่เปลี่ยน): ", 50, allow_blank=True)
    if name:
        rec["category_name"] = name
    if desc is not None:
        rec["description"] = desc
    category_table.write_at(idx, rec)
    log_action(f"Update Category id={cid}")
    print("  -> แก้ไขสำเร็จ")


def category_delete():
    print("\n-- ลบหมวดหมู่ --")
    cid = input_int("รหัสหมวดหมู่ที่ต้องการลบ: ")
    if category_table.soft_delete(cid):
        log_action(f"Delete Category id={cid}")
        print("  -> ลบสำเร็จ (soft delete)")
    else:
        print("  ! ไม่พบหมวดหมู่นี้ หรือถูกลบไปแล้ว")


# ============================================================
# 7) PRODUCT CRUD
# ============================================================

def product_add():
    print("\n-- เพิ่มสินค้าใหม่ --")
    barcode = input_str("บาร์โค้ด: ", 15)
    name = input_str("ชื่อสินค้า: ", 50)
    cat_id = category_pick_active()
    if cat_id is None:
        return
    unit = input_str("หน่วยนับ (เช่น ชิ้น, ขวด, กก.): ", 10)
    cost = input_float("ราคาทุน: ", min_val=0)
    sell = input_float("ราคาขาย: ", min_val=0)
    qty = input_int("จำนวนคงเหลือเริ่มต้น: ", min_val=0)

    pid = product_table.next_id(1001)
    rec = {"product_id": pid, "barcode": barcode, "name": name,
           "category_id": cat_id, "unit": unit, "cost_price": cost,
           "sell_price": sell, "stock_qty": qty, "status": STATUS_ACTIVE}
    product_table.append(rec)
    log_action(f"Add Product id={pid} name='{name}'")
    print(f"  -> เพิ่มสินค้าสำเร็จ (ID: {pid})")


def product_view_one():
    pid = input_int("รหัสสินค้า: ")
    idx, rec = product_table.find_index_by_id(pid)
    if rec is None:
        print("  ! ไม่พบสินค้ารหัสนี้")
        return
    _print_product_row_header()
    _print_product_row(rec)


def _print_product_row_header():
    print(f"{'ID':<6}{'บาร์โค้ด':<16}{'ชื่อสินค้า':<24}{'หมวดหมู่':<10}"
          f"{'หน่วย':<8}{'ทุน':<10}{'ขาย':<10}{'คงเหลือ':<10}{'สถานะ':<8}")
    print("-" * 102)


def _print_product_row(r):
    status = "Active" if r["status"] == STATUS_ACTIVE else "Deleted"
    print(f"{r['product_id']:<6}{r['barcode']:<16}{r['name']:<24}{r['category_id']:<10}"
          f"{r['unit']:<8}{r['cost_price']:<10.2f}{r['sell_price']:<10.2f}"
          f"{r['stock_qty']:<10}{status:<8}")


def product_view_all():
    print("\n-- รายการสินค้าทั้งหมด --")
    rows = list(product_table.all_records(include_deleted=True))
    if not rows:
        print("  (ไม่มีข้อมูล)")
        return
    _print_product_row_header()
    for _, r in rows:
        _print_product_row(r)


def product_view_filtered():
    print("\n-- ดูสินค้าแบบกรอง --")
    print("  1) กรองตามหมวดหมู่")
    print("  2) กรองสินค้าใกล้หมด (คงเหลือ <= จำนวนที่กำหนด)")
    print("  3) เฉพาะสินค้าที่ Active")
    choice = input("  เลือก: ").strip()
    rows = list(product_table.all_records(include_deleted=True))
    if choice == "1":
        cat_id = input_int("  รหัสหมวดหมู่: ")
        rows = [(i, r) for i, r in rows if r["category_id"] == cat_id]
    elif choice == "2":
        threshold = input_int("  เกณฑ์จำนวนคงเหลือ: ", min_val=0)
        rows = [(i, r) for i, r in rows if r["stock_qty"] <= threshold]
    elif choice == "3":
        rows = [(i, r) for i, r in rows if r["status"] == STATUS_ACTIVE]
    else:
        print("  ! ตัวเลือกไม่ถูกต้อง")
        return
    if not rows:
        print("  (ไม่พบสินค้าตามเงื่อนไข)")
        return
    _print_product_row_header()
    for _, r in rows:
        _print_product_row(r)


def product_view_summary():
    print("\n-- สถิติโดยสรุป (สินค้า) --")
    actives = [r for _, r in product_table.all_records(include_deleted=False)]
    total = product_table.count_records()
    deleted = total - len(actives)
    print(f"  จำนวนสินค้าทั้งหมด (records) : {total}")
    print(f"  Active                       : {len(actives)}")
    print(f"  Deleted                      : {deleted}")
    if actives:
        total_qty = sum(r["stock_qty"] for r in actives)
        low_stock = [r for r in actives if r["stock_qty"] <= 5]
        avg_sell = sum(r["sell_price"] for r in actives) / len(actives)
        print(f"  จำนวนสต็อกรวม (ชิ้น/หน่วย)    : {total_qty}")
        print(f"  สินค้าใกล้หมด (<=5)          : {len(low_stock)}")
        print(f"  ราคาขายเฉลี่ย                : {avg_sell:.2f} บาท")


def product_view_menu():
    while True:
        print("\n== เมนูดูข้อมูลสินค้า ==")
        print("1) ดูรายการเดียว")
        print("2) ดูทั้งหมด")
        print("3) ดูแบบกรอง")
        print("4) สถิติโดยสรุป")
        print("0) กลับเมนูหลัก")
        c = input("เลือก: ").strip()
        if c == "1":
            product_view_one()
        elif c == "2":
            product_view_all()
        elif c == "3":
            product_view_filtered()
        elif c == "4":
            product_view_summary()
        elif c == "0":
            break
        else:
            print("  ! ตัวเลือกไม่ถูกต้อง")


def product_update():
    print("\n-- แก้ไขสินค้า --")
    pid = input_int("รหัสสินค้าที่ต้องการแก้ไข: ")
    idx, rec = product_table.find_index_by_id(pid)
    if rec is None or rec["status"] == STATUS_DELETED:
        print("  ! ไม่พบสินค้านี้ (หรือถูกลบแล้ว)")
        return
    print(f"  ค่าปัจจุบัน: ชื่อ='{rec['name']}', ทุน={rec['cost_price']:.2f}, "
          f"ขาย={rec['sell_price']:.2f}, คงเหลือ={rec['stock_qty']}")
    name = input_str("ชื่อใหม่ (Enter=ไม่เปลี่ยน): ", 50, allow_blank=True)
    sell = input_float("ราคาขายใหม่ (Enter=ไม่เปลี่ยน): ", allow_blank=True)
    qty = input_int("จำนวนคงเหลือใหม่ (Enter=ไม่เปลี่ยน): ", allow_blank=True)
    if name:
        rec["name"] = name
    if sell is not None:
        rec["sell_price"] = sell
    if qty is not None:
        rec["stock_qty"] = qty
    product_table.write_at(idx, rec)
    log_action(f"Update Product id={pid}")
    print("  -> แก้ไขสำเร็จ")


def product_delete():
    print("\n-- ลบสินค้า --")
    pid = input_int("รหัสสินค้าที่ต้องการลบ: ")
    if product_table.soft_delete(pid):
        log_action(f"Delete Product id={pid}")
        print("  -> ลบสำเร็จ (soft delete)")
    else:
        print("  ! ไม่พบสินค้านี้ หรือถูกลบไปแล้ว")


# ============================================================
# 8) STOCK-IN (รายการนำเข้าคลัง) CRUD
# ============================================================

def stockin_add():
    print("\n-- บันทึกรายการนำเข้าคลัง --")
    pid = input_int("รหัสสินค้าที่นำเข้า: ")
    p_idx, prod = product_table.find_index_by_id(pid)
    if prod is None or prod["status"] == STATUS_DELETED:
        print("  ! ไม่พบสินค้านี้ หรือถูกลบแล้ว")
        return
    qty = input_int("จำนวนที่นำเข้า: ", min_val=1)
    cost = input_float(f"ราคาทุนต่อหน่วย (ปัจจุบัน={prod['cost_price']:.2f}, Enter=ใช้ค่าเดิม): ",
                        min_val=0, allow_blank=True)
    if cost is None:
        cost = prod["cost_price"]
    supplier = input_str("ผู้จำหน่าย/ซัพพลายเออร์: ", 30)

    import_id = stockin_table.next_id(5001)
    total_cost = qty * cost
    rec = {"import_id": import_id, "product_id": pid, "quantity": qty,
           "cost_price": cost, "total_cost": total_cost, "supplier": supplier,
           "import_date": now_ts()}
    stockin_table.append(rec)

    # update product stock_qty and cost_price
    prod["stock_qty"] += qty
    prod["cost_price"] = cost
    product_table.write_at(p_idx, prod)

    log_action(f"StockIn id={import_id} product_id={pid} qty={qty}")
    print(f"  -> บันทึกนำเข้าสำเร็จ (Import ID: {import_id}), "
          f"สินค้าคงเหลือใหม่ = {prod['stock_qty']}")


def stockin_view_all():
    print("\n-- รายการนำเข้าคลังทั้งหมด --")
    rows = list(stockin_table.all_records(include_deleted=True))
    if not rows:
        print("  (ไม่มีข้อมูล)")
        return
    print(f"{'ImportID':<10}{'ProductID':<11}{'จำนวน':<8}{'ทุน/หน่วย':<12}"
          f"{'รวม':<12}{'ผู้จำหน่าย':<20}{'วันที่':<18}")
    print("-" * 91)
    for _, r in rows:
        print(f"{r['import_id']:<10}{r['product_id']:<11}{r['quantity']:<8}"
              f"{r['cost_price']:<12.2f}{r['total_cost']:<12.2f}"
              f"{r['supplier']:<20}{fmt_ts(r['import_date']):<18}")


def stockin_view_by_product():
    pid = input_int("รหัสสินค้า: ")
    rows = [(i, r) for i, r in stockin_table.all_records(include_deleted=True)
            if r["product_id"] == pid]
    if not rows:
        print("  (ไม่พบรายการนำเข้าของสินค้านี้)")
        return
    print(f"{'ImportID':<10}{'จำนวน':<8}{'ทุน/หน่วย':<12}{'รวม':<12}{'ผู้จำหน่าย':<20}{'วันที่':<18}")
    print("-" * 80)
    for _, r in rows:
        print(f"{r['import_id']:<10}{r['quantity']:<8}{r['cost_price']:<12.2f}"
              f"{r['total_cost']:<12.2f}{r['supplier']:<20}{fmt_ts(r['import_date']):<18}")


def stockin_menu():
    while True:
        print("\n== เมนูรายการนำเข้าคลัง ==")
        print("1) บันทึกนำเข้าใหม่ (Add)")
        print("2) ดูทั้งหมด")
        print("3) ดูตามรหัสสินค้า")
        print("0) กลับเมนูหลัก")
        c = input("เลือก: ").strip()
        if c == "1":
            stockin_add()
        elif c == "2":
            stockin_view_all()
        elif c == "3":
            stockin_view_by_product()
        elif c == "0":
            break
        else:
            print("  ! ตัวเลือกไม่ถูกต้อง")


# ============================================================
# 9) REPORT GENERATION (.txt)
# ============================================================

def generate_report():
    products = list(product_table.all_records(include_deleted=True))
    categories = list(category_table.all_records(include_deleted=True))
    stockins = [r for _, r in stockin_table.all_records(include_deleted=True)]

    active_products = [r for _, r in products if r["status"] == STATUS_ACTIVE]
    deleted_products = [r for _, r in products if r["status"] == STATUS_DELETED]

    lines = []
    lines.append("Grocery Stock System - Summary Report")
    lines.append(f"Generated At : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"App Version  : {APP_VERSION}")
    lines.append("Endianness   : Little-Endian")
    lines.append("Encoding     : UTF-8 (fixed-length)")
    lines.append("")
    lines.append("-" * 90)
    lines.append(f"{'ID':<6}{'Barcode':<16}{'Name':<24}{'CatID':<7}{'Unit':<8}"
                  f"{'Cost':<9}{'Sell':<9}{'Qty':<7}{'Status':<8}")
    lines.append("-" * 90)
    for _, r in products:
        status = "Active" if r["status"] == STATUS_ACTIVE else "Deleted"
        lines.append(f"{r['product_id']:<6}{r['barcode']:<16}{r['name']:<24}"
                      f"{r['category_id']:<7}{r['unit']:<8}{r['cost_price']:<9.2f}"
                      f"{r['sell_price']:<9.2f}{r['stock_qty']:<7}{status:<8}")
    lines.append("-" * 90)
    lines.append("")

    lines.append("Summary (Products)")
    lines.append(f"- Total Products (records) : {len(products)}")
    lines.append(f"- Active Products          : {len(active_products)}")
    lines.append(f"- Deleted Products         : {len(deleted_products)}")
    if active_products:
        total_qty = sum(r["stock_qty"] for r in active_products)
        low_stock = [r for r in active_products if r["stock_qty"] <= 5]
        avg_sell = sum(r["sell_price"] for r in active_products) / len(active_products)
        lines.append(f"- Total Stock Quantity     : {total_qty}")
        lines.append(f"- Low Stock (<=5) count    : {len(low_stock)}")
        lines.append(f"- Average Sell Price       : {avg_sell:.2f}")
    lines.append("")

    lines.append("Categories")
    lines.append(f"- Total Categories : {len(categories)}")
    for _, c in categories:
        status = "Active" if c["status"] == STATUS_ACTIVE else "Deleted"
        cnt = sum(1 for r in active_products if r["category_id"] == c["category_id"])
        lines.append(f"  [{c['category_id']}] {c['category_name']} ({status}) - {cnt} product(s)")
    lines.append("")

    lines.append("Stock-In Records")
    lines.append(f"- Total Stock-In Entries : {len(stockins)}")
    if stockins:
        total_in_qty = sum(r["quantity"] for r in stockins)
        total_in_cost = sum(r["total_cost"] for r in stockins)
        lines.append(f"- Total Quantity Received : {total_in_qty}")
        lines.append(f"- Total Cost of Goods In  : {total_in_cost:.2f} THB")
    lines.append("")

    lines.append("Recent Activity Log (this session)")
    if action_log:
        for entry in action_log[-20:]:
            lines.append(f"  {entry}")
    else:
        lines.append("  (no actions this session)")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n  -> สร้างรายงานสำเร็จ: {REPORT_FILE}")


# ============================================================
# 10) MAIN MENU
# ============================================================

def print_main_menu():
    print("\n" + "=" * 50)
    print(" ระบบสต็อกสินค้าร้านขายของชำ (Grocery Stock System)")
    print("=" * 50)
    print("1) Add       - เพิ่มข้อมูล")
    print("2) Update    - แก้ไขข้อมูล")
    print("3) Delete    - ลบข้อมูล")
    print("4) View      - ดูข้อมูล")
    print("5) Generate Report (.txt)")
    print("0) Exit      - ออกจากโปรแกรม")


def add_menu():
    print("\n-- เพิ่มข้อมูล: เลือกประเภท --")
    print("1) สินค้า (Product)")
    print("2) หมวดหมู่ (Category)")
    print("3) รายการนำเข้าคลัง (Stock-In)")
    c = input("เลือก: ").strip()
    if c == "1":
        product_add()
    elif c == "2":
        category_add()
    elif c == "3":
        stockin_add()
    else:
        print("  ! ตัวเลือกไม่ถูกต้อง")


def update_menu():
    print("\n-- แก้ไขข้อมูล: เลือกประเภท --")
    print("1) สินค้า (Product)")
    print("2) หมวดหมู่ (Category)")
    c = input("เลือก: ").strip()
    if c == "1":
        product_update()
    elif c == "2":
        category_update()
    else:
        print("  ! ตัวเลือกไม่ถูกต้อง (Stock-In ไม่รองรับการแก้ไข ใช้บันทึกรายการใหม่แทน)")


def delete_menu():
    print("\n-- ลบข้อมูล: เลือกประเภท --")
    print("1) สินค้า (Product)")
    print("2) หมวดหมู่ (Category)")
    c = input("เลือก: ").strip()
    if c == "1":
        product_delete()
    elif c == "2":
        category_delete()
    else:
        print("  ! ตัวเลือกไม่ถูกต้อง")


def view_menu():
    print("\n-- ดูข้อมูล: เลือกประเภท --")
    print("1) สินค้า (Product)")
    print("2) หมวดหมู่ (Category)")
    print("3) รายการนำเข้าคลัง (Stock-In)")
    c = input("เลือก: ").strip()
    if c == "1":
        product_view_menu()
    elif c == "2":
        category_view_all()
    elif c == "3":
        stockin_menu()
    else:
        print("  ! ตัวเลือกไม่ถูกต้อง")


def safe_exit():
    print("\nกำลังปิดโปรแกรมอย่างปลอดภัย...")
    generate_report()
    print("บันทึกและปิดไฟล์เรียบร้อย. ลาก่อน!")


def main():
    while True:
        print_main_menu()
        choice = input("เลือกเมนู: ").strip()
        if choice == "1":
            add_menu()
        elif choice == "2":
            update_menu()
        elif choice == "3":
            delete_menu()
        elif choice == "4":
            view_menu()
        elif choice == "5":
            generate_report()
        elif choice == "0":
            safe_exit()
            break
        else:
            print("  ! กรุณาเลือกเมนูที่ถูกต้อง (0-5)")


if __name__ == "__main__":
    main()
