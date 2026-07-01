import subprocess
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

SMARTCTL = r"C:\Program Files\smartmontools\bin\smartctl.exe"


def run_smartctl(*args) -> dict:
    result = subprocess.run(
        [SMARTCTL, *args, "--json"],
        capture_output=True, text=True
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def get_all_disks() -> list:
    data = run_smartctl("--scan")
    return [dev["name"] for dev in data.get("devices", [])]


def print_divider(char="=", width=60):
    print(char * width)


def print_health(device: str):
    data = run_smartctl("-a", device)
    if not data:
        print(f"無法讀取 {device} 的資料，請確認以系統管理員身份執行。")
        return

    info = data.get("device", {})
    protocol = info.get("protocol", "Unknown")
    model = data.get("model_name", data.get("model_family", "Unknown"))
    serial = data.get("serial_number", "Unknown")
    capacity_bytes = data.get("user_capacity", {}).get("bytes", 0)
    capacity_gb = capacity_bytes / 1e9 if capacity_bytes else 0
    firmware = data.get("firmware_version", "Unknown")
    passed = data.get("smart_status", {}).get("passed")
    temp = data.get("temperature", {}).get("current", "N/A")
    power_on_hours = data.get("power_on_time", {}).get("hours", "N/A")

    health_str = "✓ PASSED" if passed else ("✗ FAILED" if passed is False else "? Unknown")

    print_divider()
    print(f"  裝置路徑 : {device}  ({protocol})")
    print(f"  型號     : {model}")
    print(f"  序號     : {serial}")
    print(f"  韌體     : {firmware}")
    print(f"  容量     : {capacity_gb:.0f} GB" if capacity_gb else f"  容量     : Unknown")
    print_divider("-")
    print(f"  整體健康 : {health_str}")
    print(f"  溫度     : {temp} °C")
    print(f"  使用時數 : {power_on_hours} 小時")

    # NVMe 專屬欄位
    nvme = data.get("nvme_smart_health_information_log")
    if nvme:
        spare = nvme.get("available_spare", "N/A")
        spare_thresh = nvme.get("available_spare_threshold", "N/A")
        pct_used = nvme.get("percentage_used", "N/A")
        media_errors = nvme.get("media_errors", "N/A")
        err_log = nvme.get("num_err_log_entries", "N/A")
        power_cycles = nvme.get("power_cycles", "N/A")
        unsafe_shutdowns = nvme.get("unsafe_shutdowns", "N/A")
        read_tb = nvme.get("data_units_read", 0) * 512000 / 1e12
        write_tb = nvme.get("data_units_written", 0) * 512000 / 1e12
        critical = nvme.get("critical_warning", 0)

        spare_warn = " ⚠ 低於閾值！" if isinstance(spare, int) and isinstance(spare_thresh, int) and spare <= spare_thresh else ""
        pct_warn = " ⚠ 壽命將盡！" if isinstance(pct_used, int) and pct_used >= 90 else ""
        media_warn = " ⚠ 需調查！" if isinstance(media_errors, int) and media_errors > 0 else ""
        critical_warn = " ⚠ 嚴重警告！" if critical else ""

        print_divider("-")
        print("  [NVMe 健康資訊]")
        print(f"  可用備用空間 : {spare}%（閾值 {spare_thresh}%）{spare_warn}")
        print(f"  壽命使用率   : {pct_used}%{pct_warn}")
        print(f"  嚴重警告     : {'無' if not critical else f'0x{critical:02x}'}{critical_warn}")
        print(f"  媒體錯誤數   : {media_errors}{media_warn}")
        print(f"  錯誤日誌筆數 : {err_log}")
        print(f"  電源循環次數 : {power_cycles}")
        print(f"  不正常關機   : {unsafe_shutdowns}")
        print(f"  累計讀取量   : {read_tb:.1f} TB")
        print(f"  累計寫入量   : {write_tb:.1f} TB")

    # SATA 專屬欄位
    ata = data.get("ata_smart_attributes", {}).get("table", [])
    if ata:
        key_ids = {
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
        print_divider("-")
        print("  [SATA 關鍵 SMART 屬性]")
        for attr in ata:
            aid = attr.get("id")
            if aid in key_ids:
                name = key_ids[aid]
                value = attr.get("value", "N/A")
                raw = attr.get("raw", {}).get("value", "N/A")
                worst = attr.get("worst", "N/A")
                thresh = attr.get("thresh", "N/A")
                flag = " ⚠" if isinstance(value, int) and isinstance(thresh, int) and value <= thresh else ""
                print(f"  {name:14s} : value={value:3}  worst={worst:3}  thresh={thresh:3}  raw={raw}{flag}")

    print_divider()


def main():
    print("\n=== SSD SMART 健康監控 ===\n")
    devices = get_all_disks()
    if not devices:
        print("未偵測到任何磁碟。")
        print("請確認：1) 以系統管理員身份執行  2) smartctl 路徑正確")
        sys.exit(1)

    print(f"偵測到 {len(devices)} 個磁碟：{', '.join(devices)}\n")
    for dev in devices:
        print_health(dev)
    print()


if __name__ == "__main__":
    main()
