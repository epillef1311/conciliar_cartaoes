import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve("tests/fixtures");

async function saveWorkbook(fileName, sheets) {
  const workbook = Workbook.create();
  for (const { name, rows } of sheets) {
    const worksheet = workbook.worksheets.add(name);
    const columns = Math.max(...rows.map((row) => row.length));
    const padded = rows.map((row) => [...row, ...Array(columns - row.length).fill(null)]);
    worksheet.getRangeByIndexes(0, 0, padded.length, columns).values = padded;
  }
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(root, fileName));
}

await fs.mkdir(root, { recursive: true });

await saveWorkbook("cielo/cielo_valido.xlsx", [
  {
    name: "Recebiveis_cielo_detalhe1",
    rows: [
      ["Relatorio artificial"],
      ["Filtro artificial"],
      [
        "Data de pagamento",
        "Tipo de lancamento",
        "Forma de pagamento",
        "Bandeira",
        "Valor bruto",
        "Taxa/tarifa",
        "Valor liquido",
        "Data da venda",
        "Hora da venda",
        "Codigo da autorizacao",
        "NSU/DOC",
        "Codigo da venda",
        "TID",
        "ID Pix",
      ],
      [
        "14/07/2026",
        "Venda credito",
        "Credito a vista",
        "Visa",
        "126,83",
        "-5,03",
        "121,80",
        "13/07/2026",
        "11:35",
        "AUT-1",
        "NSU-1",
        "VENDA-1",
        "TID-1",
        null,
      ],
      [
        "14/07/2026",
        "Venda Pix",
        "Pix",
        "Pix",
        "2,90",
        "-0,02",
        "2,88",
        "13/07/2026",
        "11:40",
        null,
        "DOC-2",
        "VENDA-2",
        null,
        "PIX-2",
      ],
    ],
  },
]);

await saveWorkbook("cielo/cielo_sem_cabecalho.xlsx", [
  { name: "Dados", rows: [["Relatorio"], ["Nenhuma tabela transacional"]] },
]);

const quickpayHeaders = [
  "Data da venda\u00a0",
  "Data de recebimento\u00a0",
  "Numero de Parcelas\u00a0",
  "Tipo de pagamento\u00a0",
  "Valor da Venda\u00a0",
  "Valor liquido\u00a0",
  "Taxa\u00a0",
  "Bandeira\u00a0",
  "RECEBIDO NO BANCO QUICKPAY",
];
const quickpayRows = [
  ["Relatorio artificial"],
  quickpayHeaders,
  ["13/07/2026 11:35", "14/07/2026 00:00", "1", "Credito", "126,83", "121,77", "5,03", "Visa", "121,80"],
  ["13/07/2026 11:05", "14/07/2026 00:00", "1", "Credito", "194,00", "186,26", "7,69", "MasterCard", "186,30"],
];

await saveWorkbook("quickpay/quickpay_valido.xlsx", [
  {
    name: "Lista de Transacoes",
    rows: [
      ...quickpayRows,
      [null, null, null, null, "=SUM(E3:E4)", null, "=SUM(G3:G4)", null, null],
    ],
  },
]);
await saveWorkbook("quickpay/quickpay_legado.xlsx", [
  {
    name: "Lista de Transacoes",
    rows: [
      ["Relatorio artificial"],
      quickpayHeaders.slice(0, 8),
      quickpayRows[2].slice(0, 8),
      quickpayRows[3].slice(0, 8),
      [],
      [null, null, null, null, null, null, null, null, null, null, "RECEBIDO NO BANCO QUICKPAY"],
      [null, null, null, null, null, null, null, null, null, null, "308,10"],
    ],
  },
]);
await saveWorkbook("misc/enganoso.xls.xlsx", [
  { name: "Lista de Transacoes", rows: quickpayRows },
]);
await saveWorkbook("quickpay/quickpay_sem_tabela.xlsx", [
  { name: "Lista de Transacoes", rows: [["Sem campos obrigatorios"], ["Valor aleatorio"]] },
]);
await saveWorkbook("quickpay/quickpay_tabelas_ambiguas.xlsx", [
  {
    name: "Dados",
    rows: [
      quickpayHeaders,
      ["13/07/2026 11:35", "14/07/2026", "1", "Credito", "1,00", "0,99", "0,01", "Visa", "0,99"],
      [],
      [],
      quickpayHeaders,
      ["13/07/2026 11:05", "14/07/2026", "1", "Credito", "2,00", "1,99", "0,01", "Visa", "1,99"],
    ],
  },
]);
