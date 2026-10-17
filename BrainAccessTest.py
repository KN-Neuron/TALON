"""Find and connect to a BrainAccess MAXI over Bluetooth.

Requires the official BrainAccess Python SDK on a supported computer.
"""

from brainaccess import core
from brainaccess.core.eeg_manager import EEGManager


def main() -> None:
    core.init()
    try:
        devices = list(core.scan())
        if not devices:
            print("Nie znaleziono urządzenia. Włącz MAXI i sprawdź Bluetooth.")
            return

        print("Znalezione urządzenia:")
        for index, device in enumerate(devices, 1):
            print(f"  {index}. {device.name}")

        maxi = [device for device in devices if "MAXI" in device.name.upper()]
        if len(maxi) == 1:
            device_name = maxi[0].name
            print(f"Wybieram: {device_name}")
        else:
            try:
                index = int(input("Podaj numer urządzenia z listy: ")) - 1
                device_name = devices[index].name if index >= 0 else ""
            except (ValueError, IndexError):
                device_name = ""
            if not device_name:
                print("Nieprawidłowy numer urządzenia.")
                return

        with EEGManager() as manager:
            status = manager.connect(device_name)
            if status == 2:
                print("Niekompatybilny strumień. Sprawdź wersję firmware i SDK.")
                return
            if status != 0:
                print(f"Nie udało się połączyć (kod: {status}).")
                return

            print(f"Połączono z {device_name}.")
            print(f"Bateria: {manager.get_battery_info().level}%")
            print("Liczba kanałów EEG:", manager.get_device_features().electrode_count())
            input("Naciśnij Enter, aby rozłączyć...")

        print("Rozłączono.")
    finally:
        core.close()


if __name__ == "__main__":
    main()
