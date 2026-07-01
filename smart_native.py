"""
smart_native.py
直接透過 Windows DeviceIoControl 讀取 SSD SMART 資料
不依賴 smartmontools 等外部工具
支援：NVMe / SATA SSD
需要：系統管理員權限
"""
import ctypes
import ctypes.wintypes as wt
import sys

sys.stdout.reconfigure(encoding="utf-8")

kernel32 = ctypes.windll.kernel32

# 必須明確設定 restype，否則 64-bit HANDLE 會被截斷為 32-bit
# 導致 DeviceIoControl 收到錯誤 handle → ERROR_INVALID_HANDLE(6)
kernel32.CreateFileW.restype  = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.DeviceIoControl.argtypes = [
    wt.HANDLE, wt.DWORD,
    ctypes.c_void_p, wt.DWORD,
    ctypes.c_void_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), ctypes.c_void_p,
]
kernel32.DeviceIoControl.restype = wt.BOOL

# ─── IOCTL 常數 ────────────────────────────────────────────────────────────────
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
SMART_RCV_DRIVE_DATA          = 0x0007C088
GENERIC_READ                  = 0x80000000
GENERIC_WRITE                 = 0x40000000
FILE_SHARE_READ               = 0x00000001
FILE_SHARE_WRITE              = 0x00000002
OPEN_EXISTING                 = 3
INVALID_HANDLE_VALUE          = wt.HANDLE(-1).value

StorageDeviceProperty                 = 0
StorageDeviceProtocolSpecificProperty = 50   # 0x32，Windows 11 實測值
PropertyStandardQuery                 = 0

BUS_TYPE_NAMES = {
    0: "Unknown", 1: "SCSI", 2: "ATAPI", 3: "ATA",
    4: "1394", 5: "SSA", 6: "Fibre", 7: "USB",
    8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA",
    12: "SD", 13: "MMC", 14: "Virtual", 15: "FileBackedVirtual",
    16: "Spaces", 17: "NVMe", 18: "SCM", 19: "UFS",
}

BusTypeAta  = 3
BusTypeSata = 11
BusTypeNvme = 17

ProtocolTypeNvme     = 3
NVMeDataTypeLogPage  = 2
NVME_LOG_SMART       = 0x02

ATA_CMD_SMART       = 0xB0
ATA_SMART_READ_DATA = 0xD0
ATA_SMART_CYL_LOW   = 0x4F
ATA_SMART_CYL_HIGH  = 0xC2


# ─── 結構定義 ───────────────────────────────────────────────────────────────────

class STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [
        ("PropertyId",           ctypes.c_uint32),
        ("QueryType",            ctypes.c_uint32),
        ("AdditionalParameters", ctypes.c_uint8 * 1),
    ]

class STORAGE_DEVICE_DESCRIPTOR_HEADER(ctypes.Structure):
    _fields_ = [
        ("Version",               ctypes.c_uint32),
        ("Size",                  ctypes.c_uint32),
        ("DeviceType",            ctypes.c_uint8),
        ("DeviceTypeModifier",    ctypes.c_uint8),
        ("RemovableMedia",        ctypes.c_uint8),
        ("CommandQueueing",       ctypes.c_uint8),
        ("VendorIdOffset",        ctypes.c_uint32),
        ("ProductIdOffset",       ctypes.c_uint32),
        ("ProductRevisionOffset", ctypes.c_uint32),
        ("SerialNumberOffset",    ctypes.c_uint32),
        ("BusType",               ctypes.c_uint32),
        ("RawPropertiesLength",   ctypes.c_uint32),
    ]

class STORAGE_PROTOCOL_SPECIFIC_DATA(ctypes.Structure):
    # Windows 11 實測需使用完整版（68 bytes），原始 32 bytes 版本會 err=87
    _fields_ = [
        ("ProtocolType",                ctypes.c_uint32),
        ("DataType",                    ctypes.c_uint32),
        ("ProtocolDataRequestValue",    ctypes.c_uint32),
        ("ProtocolDataRequestSubValue", ctypes.c_uint32),
        ("ProtocolDataOffset",          ctypes.c_uint32),
        ("ProtocolDataLength",          ctypes.c_uint32),
        ("FixedProtocolReturnData",     ctypes.c_uint32),
        ("ProtocolDataRequestSubValue2",ctypes.c_uint32),
        ("ProtocolDataRequestSubValue3",ctypes.c_uint32),
        ("ProtocolDataRequestSubValue4",ctypes.c_uint32),
        ("ProtocolDataRequestSubValue5",ctypes.c_uint32),
        ("Reserved",                    ctypes.c_uint32 * 6),
    ]

class NVME_HEALTH_INFO_LOG(ctypes.Structure):
    """NVMe Spec — Log Page 02h，固定 512 bytes"""
    _fields_ = [
        ("CriticalWarning",        ctypes.c_uint8),
        ("Temperature",            ctypes.c_uint8 * 2),
        ("AvailableSpare",         ctypes.c_uint8),
        ("AvailableSpareThreshold",ctypes.c_uint8),
        ("PercentageUsed",         ctypes.c_uint8),
        ("Reserved1",              ctypes.c_uint8 * 26),
        ("DataUnitsRead",          ctypes.c_uint8 * 16),
        ("DataUnitsWritten",       ctypes.c_uint8 * 16),
        ("HostReadCommands",       ctypes.c_uint8 * 16),
        ("HostWriteCommands",      ctypes.c_uint8 * 16),
        ("ControllerBusyTime",     ctypes.c_uint8 * 16),
        ("PowerCycles",            ctypes.c_uint8 * 16),
        ("PowerOnHours",           ctypes.c_uint8 * 16),
        ("UnsafeShutdowns",        ctypes.c_uint8 * 16),
        ("MediaErrors",            ctypes.c_uint8 * 16),
        ("ErrorInfoLogEntries",    ctypes.c_uint8 * 16),
        ("Reserved2",              ctypes.c_uint8 * 320),
    ]

class IDEREGS(ctypes.Structure):
    _fields_ = [
        ("bFeaturesReg",    ctypes.c_uint8),
        ("bSectorCountReg", ctypes.c_uint8),
        ("bSectorNumberReg",ctypes.c_uint8),
        ("bCylLowReg",      ctypes.c_uint8),
        ("bCylHighReg",     ctypes.c_uint8),
        ("bDriveHeadReg",   ctypes.c_uint8),
        ("bCommandReg",     ctypes.c_uint8),
        ("bReserved",       ctypes.c_uint8),
    ]

class SENDCMDINPARAMS(ctypes.Structure):
    _fields_ = [
        ("cBufferSize",  ctypes.c_uint32),
        ("irDriveRegs",  IDEREGS),
        ("bDriveNumber", ctypes.c_uint8),
        ("bReserved",    ctypes.c_uint8 * 3),
        ("dwReserved",   ctypes.c_uint32 * 4),
        ("bBuffer",      ctypes.c_uint8 * 1),
    ]

class DRIVERSTATUS(ctypes.Structure):
    _fields_ = [
        ("bDriverError", ctypes.c_uint8),
        ("bIDEError",    ctypes.c_uint8),
        ("bReserved",    ctypes.c_uint8 * 2),
        ("dwReserved",   ctypes.c_uint32 * 2),
    ]

class SENDCMDOUTPARAMS(ctypes.Structure):
    _fields_ = [
        ("cBufferSize",  ctypes.c_uint32),
        ("DriverStatus", DRIVERSTATUS),
        ("bBuffer",      ctypes.c_uint8 * 512),
    ]


# ─── 工具函式 ───────────────────────────────────────────────────────────────────

def le128(raw_bytes) -> int:
    return int.from_bytes(bytes(raw_bytes), "little")

def units_to_tb(raw_bytes) -> float:
    return le128(raw_bytes) * 512_000 / 1e12

def warn(cond: bool, msg: str = " ⚠") -> str:
    return msg if cond else ""

def divider(char="=", w=60):
    print(char * w)


# ─── 磁碟存取 ───────────────────────────────────────────────────────────────────

def open_drive(path: str):
    handle = kernel32.CreateFileW(
        path,
        GENERIC_READ | GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None, OPEN_EXISTING, 0, None
    )
    if handle == INVALID_HANDLE_VALUE:
        err = kernel32.GetLastError()
        raise PermissionError(f"無法開啟 {path}，錯誤碼 {err}，請以系統管理員身份執行")
    return handle

def ioctl(handle, code, in_buf, out_buf) -> bool:
    br = wt.DWORD(0)
    return bool(kernel32.DeviceIoControl(
        handle, code,
        ctypes.byref(in_buf), ctypes.sizeof(in_buf),
        ctypes.byref(out_buf), ctypes.sizeof(out_buf),
        ctypes.byref(br), None
    ))

def enumerate_drives() -> list:
    drives = []
    for i in range(16):
        path = rf"\\.\PhysicalDrive{i}"
        h = kernel32.CreateFileW(
            path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None, OPEN_EXISTING, 0, None
        )
        if h != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(h)
            drives.append(path)
    return drives


# ─── 偵測 Bus Type ──────────────────────────────────────────────────────────────

def get_bus_type(handle) -> int:
    in_buf  = STORAGE_PROPERTY_QUERY()
    in_buf.PropertyId = StorageDeviceProperty
    in_buf.QueryType  = PropertyStandardQuery
    out_buf = (ctypes.c_uint8 * 1024)()
    br = wt.DWORD(0)

    ok = kernel32.DeviceIoControl(
        handle, IOCTL_STORAGE_QUERY_PROPERTY,
        ctypes.byref(in_buf), ctypes.sizeof(in_buf),
        ctypes.byref(out_buf), 1024,
        ctypes.byref(br), None
    )
    if not ok:
        return -1

    desc = STORAGE_DEVICE_DESCRIPTOR_HEADER.from_buffer_copy(bytes(out_buf))
    return desc.BusType


# ─── NVMe SMART ────────────────────────────────────────────────────────────────

def read_nvme_smart(handle) -> dict:
    PROTO_SIZE = ctypes.sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA)
    DATA_SIZE  = 512
    QUERY_BASE = 8  # offsetof(STORAGE_PROPERTY_QUERY, AdditionalParameters)

    total = QUERY_BASE + PROTO_SIZE + DATA_SIZE
    buf   = (ctypes.c_uint8 * total)()

    q = STORAGE_PROPERTY_QUERY.from_buffer(buf)
    q.PropertyId = StorageDeviceProtocolSpecificProperty
    q.QueryType  = PropertyStandardQuery

    p = STORAGE_PROTOCOL_SPECIFIC_DATA.from_buffer(buf, QUERY_BASE)
    p.ProtocolType                = ProtocolTypeNvme
    p.DataType                    = NVMeDataTypeLogPage
    p.ProtocolDataRequestValue    = NVME_LOG_SMART
    p.ProtocolDataRequestSubValue = 0
    p.ProtocolDataOffset          = PROTO_SIZE
    p.ProtocolDataLength          = DATA_SIZE

    br = wt.DWORD(0)
    ok = kernel32.DeviceIoControl(
        handle, IOCTL_STORAGE_QUERY_PROPERTY,
        ctypes.byref(buf), total,
        ctypes.byref(buf), total,
        ctypes.byref(br), None
    )
    if not ok:
        raise OSError(f"NVMe SMART IOCTL 失敗，錯誤碼 {kernel32.GetLastError()}")

    offset = QUERY_BASE + PROTO_SIZE
    log = NVME_HEALTH_INFO_LOG.from_buffer_copy(bytes(buf)[offset:offset + 512])
    temp_k = int.from_bytes(bytes(log.Temperature), "little")

    return {
        "protocol":          "NVMe",
        "critical_warning":  log.CriticalWarning,
        "temperature":       temp_k - 273,
        "available_spare":   log.AvailableSpare,
        "spare_threshold":   log.AvailableSpareThreshold,
        "percentage_used":   log.PercentageUsed,
        "read_tb":           units_to_tb(log.DataUnitsRead),
        "write_tb":          units_to_tb(log.DataUnitsWritten),
        "power_on_hours":    le128(log.PowerOnHours),
        "power_cycles":      le128(log.PowerCycles),
        "unsafe_shutdowns":  le128(log.UnsafeShutdowns),
        "media_errors":      le128(log.MediaErrors),
        "error_log_entries": le128(log.ErrorInfoLogEntries),
    }


# ─── SATA SMART ────────────────────────────────────────────────────────────────

SATA_KEY_ATTRS = {
    5:   "重新分配磁區數",
    9:   "使用時數",
    177: "磨耗均衡計數",
    179: "保留區塊剩餘",
    190: "溫度差值",
    194: "溫度",
    196: "重新分配事件數",
    197: "待處理磁區數",
    198: "無法修正磁區數",
    231: "SSD 壽命剩餘",
    233: "媒體磨耗指標",
}

def read_sata_smart(handle) -> dict:
    in_buf = SENDCMDINPARAMS()
    in_buf.cBufferSize                = 512
    in_buf.irDriveRegs.bFeaturesReg   = ATA_SMART_READ_DATA
    in_buf.irDriveRegs.bSectorCountReg  = 1
    in_buf.irDriveRegs.bSectorNumberReg = 1
    in_buf.irDriveRegs.bCylLowReg    = ATA_SMART_CYL_LOW
    in_buf.irDriveRegs.bCylHighReg   = ATA_SMART_CYL_HIGH
    in_buf.irDriveRegs.bDriveHeadReg = 0xA0
    in_buf.irDriveRegs.bCommandReg   = ATA_CMD_SMART

    out_buf = SENDCMDOUTPARAMS()
    if not ioctl(handle, SMART_RCV_DRIVE_DATA, in_buf, out_buf):
        raise OSError(f"SATA SMART IOCTL 失敗，錯誤碼 {kernel32.GetLastError()}")

    raw = bytes(out_buf.bBuffer)
    attrs = {}
    for i in range(30):
        base    = 2 + i * 12
        attr_id = raw[base]
        if attr_id == 0:
            continue
        attrs[attr_id] = {
            "value": raw[base + 3],
            "worst": raw[base + 4],
            "raw":   int.from_bytes(raw[base + 5: base + 11], "little"),
        }
    return {"protocol": "SATA", "attrs": attrs}


# ─── 輸出 ───────────────────────────────────────────────────────────────────────

def print_nvme(path: str, d: dict):
    health = "✓ PASSED" if d["critical_warning"] == 0 else "✗ WARNING"
    divider()
    print(f"  裝置         : {path}  (NVMe)")
    divider("-")
    print(f"  整體健康     : {health}")
    print(f"  溫度         : {d['temperature']} °C")
    print(f"  可用備用空間 : {d['available_spare']}%（閾值 {d['spare_threshold']}%）"
          + warn(d["available_spare"] <= d["spare_threshold"], " ⚠ 低於閾值！"))
    print(f"  壽命使用率   : {d['percentage_used']}%"
          + warn(d["percentage_used"] >= 90, " ⚠ 壽命將盡！"))
    print(f"  媒體錯誤數   : {d['media_errors']}"
          + warn(d["media_errors"] > 0, " ⚠ 需調查！"))
    print(f"  錯誤日誌筆數 : {d['error_log_entries']}")
    print(f"  電源循環次數 : {d['power_cycles']}")
    print(f"  不正常關機   : {d['unsafe_shutdowns']}")
    print(f"  累計讀取量   : {d['read_tb']:.2f} TB")
    print(f"  累計寫入量   : {d['write_tb']:.2f} TB")
    print(f"  使用時數     : {d['power_on_hours']} 小時")
    divider()

def print_sata(path: str, d: dict):
    attrs = d["attrs"]
    divider()
    print(f"  裝置  : {path}  (SATA)")
    divider("-")
    print(f"  {'ID':>3}  {'屬性名稱':<16}  {'Value':>5}  {'Worst':>5}  {'Raw':>12}")
    divider("-")
    for aid, name in SATA_KEY_ATTRS.items():
        if aid not in attrs:
            continue
        a = attrs[aid]
        print(f"  {aid:>3}  {name:<16}  {a['value']:>5}  {a['worst']:>5}  {a['raw']:>12}"
              + warn(a["value"] <= 10))
    divider()


# ─── 主程式 ─────────────────────────────────────────────────────────────────────

def probe_drive(path: str):
    try:
        handle = open_drive(path)
    except PermissionError as e:
        return None, str(e)

    try:
        bus = get_bus_type(handle)
        bus_name = BUS_TYPE_NAMES.get(bus, f"未知({bus})")

        if bus == BusTypeNvme:
            return read_nvme_smart(handle), bus_name
        if bus in (BusTypeAta, BusTypeSata):
            return read_sata_smart(handle), bus_name

        try:
            return read_nvme_smart(handle), f"NVMe（BusType={bus_name}）"
        except OSError:
            pass
        try:
            return read_sata_smart(handle), f"SATA（BusType={bus_name}）"
        except OSError:
            pass

        return None, f"BusType={bus_name}，NVMe 與 SATA 均不支援"

    except OSError as e:
        return None, str(e)
    finally:
        kernel32.CloseHandle(handle)


def main():
    print("\n=== SSD SMART 健康監控（Native DeviceIoControl）===\n")

    drives = enumerate_drives()
    if not drives:
        print("未偵測到任何磁碟，請確認以系統管理員身份執行。")
        sys.exit(1)

    print(f"偵測到 {len(drives)} 個磁碟，逐一量測...\n")

    found = 0
    for path in drives:
        data, info = probe_drive(path)
        if data is None:
            print(f"  {path}：跳過（{info}）")
            continue
        found += 1
        if data["protocol"] == "NVMe":
            print_nvme(path, data)
        else:
            print_sata(path, data)

    if found == 0:
        print("\n未能讀取任何磁碟的 SMART 資料。")
        print("可能原因：")
        print("  1. 在 VM 環境中，虛擬磁碟不支援 NVMe/SATA Protocol IOCTL")
        print("  2. 請改用 smartmontools（smartctl）直接存取硬體")
    print()


if __name__ == "__main__":
    main()
