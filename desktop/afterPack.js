/**
 * Hook afterPack do electron-builder: aplica ícone e metadata no ProspectOS.exe
 * via rcedit (substitui o signAndEditExecutable, desligado porque o pacote
 * winCodeSign exige privilégio de symlink que nem todo Windows tem).
 */

const path = require("path");
const { rcedit } = require("rcedit");

module.exports = async function aposEmpacotar(contexto) {
  const exe = path.join(contexto.appOutDir, "ProspectOS.exe");
  const versao = contexto.packager.appInfo.version;

  await rcedit(exe, {
    icon: path.join(__dirname, "prospectos.ico"),
    "version-string": {
      ProductName: "ProspectOS",
      FileDescription: "ProspectOS - prospecção de leads com IA",
      CompanyName: "nando0x",
      LegalCopyright: "MIT License",
      OriginalFilename: "ProspectOS.exe",
    },
    "file-version": versao,
    "product-version": versao,
  });
  console.log(`  • rcedit aplicado (icone + metadata) em ${exe}`);
};
