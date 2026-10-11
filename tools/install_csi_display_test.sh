#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_file="${project_root}/tools/42_csi_display_test"
monitor_file="${project_root}/tools/20_csi_monitor.conf"
[[ ${EUID} -eq 0 ]] || { echo 'Run with sudo bash tools/install_csi_display_test.sh'; exit 1; }
[[ -f /boot/vmlinuz-4.15.0-213-generic && -f /boot/initrd.img-4.15.0-213-generic ]]
[[ "$(findmnt -n -o UUID /)" == daa68b2d-cb72-480c-850b-36d9b330fbc0 ]] || {
    echo 'This configuration is only for the diagnosed RXPC root filesystem.' >&2
    exit 1
}
grub-script-check <(sh "${source_file}")
backup_dir="$(mktemp -d /var/backups/csi-display.XXXXXXXX)"
cp -a /etc/default/grub /boot/grub/grub.cfg "${backup_dir}/"
for existing in /etc/grub.d/42_csi_display_test /etc/default/grub.d/99_csi_display_test.cfg /etc/X11/xorg.conf.d/20-csi-monitor.conf; do
    if [[ -e "${existing}" ]]; then cp -a "${existing}" "${backup_dir}/"; fi
done
install -m 0755 "${source_file}" /etc/grub.d/42_csi_display_test
install -d /etc/default/grub.d
printf '%s\n' 'GRUB_TIMEOUT_STYLE=menu' 'GRUB_TIMEOUT=10' > /etc/default/grub.d/99_csi_display_test.cfg
install -d /etc/X11/xorg.conf.d
install -m 0644 "${monitor_file}" /etc/X11/xorg.conf.d/20-csi-monitor.conf
update-grub
grub-script-check /boot/grub/grub.cfg
echo "Installed optional CSI display test entries. Backup: ${backup_dir}"
echo 'Default boot selection is unchanged. No reboot performed.'
