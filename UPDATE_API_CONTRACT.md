# Contrato de atualização do MKT

O aplicativo consulta, sem autenticação e em segundo plano, o manifesto da
release mais recente:

`GET https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/releases/latest/download/latest.json`

Quando não houver atualização, o servidor pode responder `204 No Content` ou
um manifesto com a mesma versão. Quando houver, deve responder JSON:

```json
{
  "version": "2.7.2",
  "channel": "stable",
  "downloadUrl": "https://github.com/luizphotoshop25-prog/AlbionMKT-Releases/releases/download/v2.7.2/MKT_Update_2.7.2.zip",
  "sha256": "64-caracteres-hexadecimais",
  "size": 123456789,
  "mandatory": false,
  "minimumVersion": "2.7.1",
  "signature": null
}
```

Regras obrigatórias da publicação:

- publicar primeiro o ZIP e somente depois o manifesto;
- usar exclusivamente releases do repositório público
  `luizphotoshop25-prog/AlbionMKT-Releases`;
- manter a correspondência exata entre tag `v<versão>`, versão do manifesto e
  nome `MKT_Update_<versão>.zip`;
- calcular `size` e SHA-256 do arquivo final, sem transformações posteriores;
- manter o ZIP com uma única raiz `app/` e `app/MKT.exe`;
- nunca incluir chaves, tokens, banco de licenças ou código do bot do Discord;
- preservar versões anteriores para rollback operacional;
- permitir a consulta apenas como leitura; emissão e revogação de keys ficam na
  API independente e nunca usam o repositório público.

O cliente baixa pelo atualizador externo, confere tamanho e SHA-256, encerra o
MKT, troca a pasta de forma atômica e guarda a instalação anterior em
`MKT.previous`. Em caso de falha durante a troca, restaura automaticamente a
versão anterior.

