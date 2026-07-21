const path = require("path");

module.exports = async function aposEmpacotar(contexto) {
  if (contexto.electronPlatformName !== "win32") {
    console.log("  • rcedit ignorado (plataforma:", contexto.electronPlatformName, ")");
    return;
  }

  const { rcedit } = require("rcedit");
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
