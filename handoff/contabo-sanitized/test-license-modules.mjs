import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const temporary = await mkdtemp(path.join(os.tmpdir(), "albionmkt-license-modules-"));
const originalDirectory = process.cwd();

try {
  process.chdir(temporary);
  process.env.LICENSE_ENCRYPTION_KEY = "11".repeat(32);
  process.env.LICENSE_PEPPER = "test-pepper-license-modules";

  const storeUrl = pathToFileURL(
    path.join(originalDirectory, "src", "license-store.js")
  ).href;
  const {
    createLicense,
    formatLicenseModules,
    modulesForAccess,
    updateLicense,
    validateLicense
  } = await import(storeUrl);

  const purchase = await createLicense({
    sourceId: "test:purchase",
    modules: modulesForAccess("purchase")
  });
  assert.deepEqual(purchase.modules, ["purchase_orders"]);

  const sales = await createLicense({
    sourceId: "test:sales",
    modules: modulesForAccess("sales")
  });
  assert.deepEqual(sales.modules, ["sales_orders"]);

  const complete = await createLicense({
    sourceId: "test:complete",
    modules: modulesForAccess("complete")
  });
  assert.deepEqual(complete.modules, ["purchase_orders", "sales_orders"]);
  assert.equal(formatLicenseModules(complete.modules), "Compra + Venda (Ciclo Automatico)");

  const validation = await validateLicense({
    licenseKey: complete.licenseKey,
    hwid: "test-device",
    activate: true
  });
  assert.equal(validation.valid, true);
  assert.deepEqual(validation.modules, ["purchase_orders", "sales_orders"]);

  const updated = await updateLicense(sales.id, "set-modules", {
    modules: modulesForAccess("purchase")
  });
  assert.deepEqual(updated.modules, ["purchase_orders"]);

  console.log("LICENSE_MODULES_TEST=OK");
} finally {
  process.chdir(originalDirectory);
  await rm(temporary, { recursive: true, force: true });
}
