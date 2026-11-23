const express = require('express');
const cors = require('cors');
const bcrypt = require('bcrypt');
const conexao = require('./conexao');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.get('/', (req, res) => {
  res.json({ mensagem: 'API FacilitaMEI rodando com sucesso!' });
});

// ==========================================
// 1. AUTENTICAÇÃO E EMPRESA ("Registros Empresas")
// ==========================================
app.post('/cadastro', async (req, res) => {
  const { nome, cpf_cnpj, email, senha } = req.body;
  if (!nome || !cpf_cnpj || !email || !senha) {
    return res.status(400).json({ erro: 'Preencha todos os campos obrigatórios.' });
  }

  try {
    const saltRounds = 10;
    const senhaHash = await bcrypt.hash(senha, saltRounds);

    const query = `
      INSERT INTO "Registros Empresas" ("Nome", "CPF_CNPJ", "Email", "Senha") 
      VALUES ($1, $2, $3, $4) 
      RETURNING id, created_at, "Nome", "CPF_CNPJ", "Email"
    `;
    const resultado = await conexao.query(query, [nome, cpf_cnpj, email, senhaHash]);

    return res.status(201).json({
      mensagem: 'Cadastro realizado com sucesso!',
      usuario: resultado.rows[0]
    });
  } catch (erro) {
    console.error('Erro ao cadastrar:', erro);
    if (erro.code === '23505') {
      return res.status(400).json({ erro: 'Este CPF/CNPJ ou Email já está cadastrado.' });
    }
    return res.status(500).json({ erro: 'Erro interno no servidor ao cadastrar.' });
  }
});

app.post('/login', async (req, res) => {
  const { email, senha } = req.body;
  if (!email || !senha) {
    return res.status(400).json({ erro: 'Informe o email e a senha.' });
  }

  try {
    const query = 'SELECT * FROM "Registros Empresas" WHERE "Email" = $1';
    const resultado = await conexao.query(query, [email]);

    if (resultado.rows.length === 0) {
      return res.status(401).json({ erro: 'Email não encontrado ou senha incorreta.' });
    }

    const usuario = resultado.rows[0];
    const senhaValida = await bcrypt.compare(senha, usuario.Senha);

    if (!senhaValida) {
      return res.status(401).json({ erro: 'Email não encontrado ou senha incorreta.' });
    }

    return res.json({
      mensagem: 'Login realizado com sucesso!',
      usuario: {
        id: usuario.id,
        nome: usuario.Nome,
        cpf_cnpj: usuario.CPF_CNPJ,
        email: usuario.Email
      }
    });
  } catch (erro) {
    console.error('Erro ao fazer login:', erro);
    return res.status(500).json({ erro: 'Erro interno no servidor ao realizar login.' });
  }
});

app.get('/empresa/:id', async (req, res) => {
  const { id } = req.params;
  try {
    const resultado = await conexao.query(
      'SELECT id, "Nome" AS nome, "CPF_CNPJ" AS cnpj, "Email" AS email FROM "Registros Empresas" WHERE id = $1',
      [id]
    );
    if (resultado.rows.length === 0) {
      return res.status(404).json({ erro: 'Empresa não encontrada.' });
    }
    return res.json(resultado.rows[0]);
  } catch (erro) {
    console.error('Erro ao buscar dados da empresa:', erro);
    return res.status(500).json({ erro: 'Erro interno ao buscar empresa.' });
  }
});

app.put('/empresa/:id', async (req, res) => {
  const { id } = req.params;
  const { nome, cnpj, email } = req.body;

  if (!nome || !email) {
    return res.status(400).json({ erro: 'Nome da empresa e e-mail são obrigatórios.' });
  }

  try {
    const resultado = await conexao.query(
      `UPDATE "Registros Empresas"
       SET "Nome" = $1, "CPF_CNPJ" = $2, "Email" = $3
       WHERE id = $4
       RETURNING id, "Nome" AS nome, "CPF_CNPJ" AS cnpj, "Email" AS email`,
      [nome, cnpj || '', email, id]
    );

    if (resultado.rowCount === 0) {
      return res.status(404).json({ erro: 'Empresa não encontrada.' });
    }

    return res.json({ mensagem: 'Dados atualizados com sucesso!', empresa: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao atualizar empresa:', erro);
    if (erro.code === '23505') {
      return res.status(400).json({ erro: 'Este CPF/CNPJ ou e-mail já está cadastrado em outra conta.' });
    }
    return res.status(500).json({ erro: 'Erro interno ao atualizar dados da empresa.' });
  }
});

// ==========================================
// 2. PRODUTOS (tabela: produtos)
// ==========================================
app.get('/produtos', async (req, res) => {
  const { empresa_id } = req.query;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM produtos WHERE empresa_id = $1 ORDER BY id DESC',
      [empresa_id]
    );
    res.json(resultado.rows);
  } catch (erro) {
    console.error('Erro ao buscar produtos:', erro);
    res.status(500).json({ erro: 'Erro interno ao consultar produtos' });
  }
});

app.post('/produtos', async (req, res) => {
  const {
    empresa_id, nome, sku, categoria, descricao,
    preco, custo, estoque_inicial, unidade, estoque_minimo, status
  } = req.body;

  if (!empresa_id || !nome || !sku || preco === undefined) {
    return res.status(400).json({ erro: 'Empresa, Nome, SKU e Preço são obrigatórios.' });
  }

  try {
    const query = `
      INSERT INTO produtos (empresa_id, nome, sku, categoria, descricao, preco, custo, estoque_inicial, unidade, estoque_minimo, status)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
      RETURNING *
    `;
    const values = [
      empresa_id, nome, sku, categoria || '', descricao || '',
      preco, custo || 0, estoque_inicial || 0,
      unidade || 'Unidade (un)', estoque_minimo || 0, status || 'Ativo'
    ];
    const resultado = await conexao.query(query, values);
    return res.status(201).json({ mensagem: 'Produto cadastrado com sucesso!', produto: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao cadastrar produto:', erro);
    if (erro.code === '23505') {
      return res.status(400).json({ erro: 'Você já possui um produto cadastrado com este SKU.' });
    }
    return res.status(500).json({ erro: 'Erro interno ao salvar produto.' });
  }
});

app.get('/produtos/:id', async (req, res) => {
  const { id } = req.params;
  const { empresa_id } = req.query;

  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM produtos WHERE id = $1 AND empresa_id = $2',
      [id, empresa_id]
    );

    if (resultado.rows.length === 0) {
      return res.status(404).json({ erro: 'Produto não encontrado.' });
    }

    return res.json(resultado.rows[0]);
  } catch (erro) {
    console.error('Erro ao buscar produto:', erro);
    return res.status(500).json({ erro: 'Erro interno ao buscar produto.' });
  }
});

app.put('/produtos/:id', async (req, res) => {
  const { id } = req.params;
  const {
    empresa_id, nome, sku, categoria, descricao,
    preco, custo, estoque_inicial, unidade, estoque_minimo, status
  } = req.body;

  if (!empresa_id || !nome || !sku || preco === undefined) {
    return res.status(400).json({ erro: 'Empresa, Nome, SKU e Preço são obrigatórios.' });
  }

  try {
    const query = `
      UPDATE produtos
      SET nome = $1, sku = $2, categoria = $3, descricao = $4,
          preco = $5, custo = $6, estoque_inicial = $7, unidade = $8,
          estoque_minimo = $9, status = $10
      WHERE id = $11 AND empresa_id = $12
      RETURNING *
    `;
    const values = [
      nome, sku, categoria || '', descricao || '',
      preco, custo || 0, estoque_inicial || 0,
      unidade || 'Unidade (un)', estoque_minimo || 0, status || 'Ativo',
      id, empresa_id
    ];

    const resultado = await conexao.query(query, values);

    if (resultado.rowCount === 0) {
      return res.status(404).json({ erro: 'Produto não encontrado.' });
    }

    return res.json({ mensagem: 'Produto atualizado com sucesso!', produto: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao atualizar produto:', erro);
    if (erro.code === '23505') {
      return res.status(400).json({ erro: 'Você já possui outro produto cadastrado com este SKU.' });
    }
    return res.status(500).json({ erro: 'Erro interno ao atualizar produto.' });
  }
});

app.delete('/produtos/:id', async (req, res) => {
  const { id } = req.params;
  const { empresa_id } = req.query;

  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'DELETE FROM produtos WHERE id = $1 AND empresa_id = $2 RETURNING *',
      [id, empresa_id]
    );

    if (resultado.rowCount === 0) {
      return res.status(404).json({ erro: 'Produto não encontrado.' });
    }

    return res.json({ mensagem: 'Produto excluído com sucesso!' });
  } catch (erro) {
    console.error('Erro ao excluir produto:', erro);
    return res.status(500).json({ erro: 'Erro interno ao excluir produto.' });
  }
});

// ==========================================
// 3. CLIENTES (tabela: clientes)
// ==========================================
app.get('/clientes', async (req, res) => {
  const { empresa_id } = req.query;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM clientes WHERE empresa_id = $1 ORDER BY id DESC',
      [empresa_id]
    );
    res.json(resultado.rows);
  } catch (erro) {
    console.error('Erro ao buscar clientes:', erro);
    res.status(500).json({ erro: 'Erro ao buscar clientes' });
  }
});

app.get('/clientes/:id', async (req, res) => {
  const { id } = req.params;
  const { empresa_id } = req.query;

  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM clientes WHERE id = $1 AND empresa_id = $2',
      [id, empresa_id]
    );

    if (resultado.rows.length === 0) {
      return res.status(404).json({ erro: 'Cliente não encontrado.' });
    }

    return res.json(resultado.rows[0]);
  } catch (erro) {
    console.error('Erro ao buscar cliente:', erro);
    return res.status(500).json({ erro: 'Erro interno ao buscar cliente.' });
  }
});

app.post('/clientes', async (req, res) => {
  const {
    empresa_id, nome, tipo_pessoa, documento, telefone, email, status,
    cep, logradouro, numero, complemento, bairro, cidade, uf,
    forma_pagamento, prazo_pagamento, limite_credito, categoria_receita, observacoes
  } = req.body;

  if (!empresa_id || !nome) {
    return res.status(400).json({ erro: 'Empresa e nome do cliente são obrigatórios.' });
  }

  try {
    const query = `
      INSERT INTO clientes (empresa_id, nome, tipo_pessoa, documento, telefone, email, status, cep, logradouro, numero, complemento, bairro, cidade, uf, forma_pagamento, prazo_pagamento, limite_credito, categoria_receita, observacoes)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
      RETURNING *
    `;
    const values = [
      empresa_id, nome, tipo_pessoa, documento, telefone, email, status || 'Ativo',
      cep, logradouro, numero, complemento, bairro, cidade, uf,
      forma_pagamento, prazo_pagamento, limite_credito || 0, categoria_receita, observacoes
    ];
    const resultado = await conexao.query(query, values);
    return res.status(201).json({ mensagem: 'Cliente cadastrado com sucesso!', cliente: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao cadastrar cliente:', erro);
    return res.status(500).json({ erro: 'Erro interno ao salvar cliente' });
  }
});

app.put('/clientes/:id', async (req, res) => {
  const { id } = req.params;
  const {
    empresa_id, nome, tipo_pessoa, documento, telefone, email, status,
    cep, logradouro, numero, complemento, bairro, cidade, uf,
    forma_pagamento, prazo_pagamento, limite_credito, categoria_receita, observacoes
  } = req.body;

  if (!empresa_id || !nome) {
    return res.status(400).json({ erro: 'Empresa e nome do cliente são obrigatórios.' });
  }

  try {
    const query = `
      UPDATE clientes
      SET nome = $1, tipo_pessoa = $2, documento = $3, telefone = $4, email = $5,
          status = $6, cep = $7, logradouro = $8, numero = $9, complemento = $10,
          bairro = $11, cidade = $12, uf = $13, forma_pagamento = $14,
          prazo_pagamento = $15, limite_credito = $16, categoria_receita = $17,
          observacoes = $18
      WHERE id = $19 AND empresa_id = $20
      RETURNING *
    `;
    const values = [
      nome, tipo_pessoa, documento, telefone, email,
      status || 'Ativo', cep, logradouro, numero, complemento,
      bairro, cidade, uf, forma_pagamento,
      prazo_pagamento, limite_credito || 0, categoria_receita,
      observacoes, id, empresa_id
    ];

    const resultado = await conexao.query(query, values);

    if (resultado.rowCount === 0) {
      return res.status(404).json({ erro: 'Cliente não encontrado.' });
    }

    return res.json({ mensagem: 'Cliente atualizado com sucesso!', cliente: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao atualizar cliente:', erro);
    return res.status(500).json({ erro: 'Erro interno ao atualizar cliente.' });
  }
});

// ==========================================
// 4. MOVIMENTAÇÕES (tabela: movimentacoes)
// ==========================================
app.get('/movimentacoes', async (req, res) => {
  const { empresa_id } = req.query;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM movimentacoes WHERE empresa_id = $1 ORDER BY data DESC, id DESC',
      [empresa_id]
    );
    res.json(resultado.rows);
  } catch (erro) {
    console.error('Erro ao consultar movimentações:', erro);
    res.status(500).json({ erro: 'Erro ao consultar movimentações' });
  }
});

app.post('/movimentacoes', async (req, res) => {
  const { empresa_id, data, tipo, categoria, forma, valor, descricao } = req.body;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const query = `
      INSERT INTO movimentacoes (empresa_id, data, tipo, categoria, forma, valor, descricao)
      VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
    `;
    const resultado = await conexao.query(query, [empresa_id, data, tipo, categoria, forma, valor, descricao]);
    return res.status(201).json({ mensagem: 'Lançamento salvo com sucesso!', item: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao salvar movimentação:', erro);
    return res.status(500).json({ erro: 'Erro ao salvar movimentação' });
  }
});

app.delete('/movimentacoes/:id', async (req, res) => {
  const { id } = req.params;
  const { empresa_id } = req.query;

  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'DELETE FROM movimentacoes WHERE id = $1 AND empresa_id = $2 RETURNING *',
      [id, empresa_id]
    );

    if (resultado.rowCount === 0) {
      return res.status(404).json({ erro: 'Lançamento não encontrado.' });
    }

    return res.json({ mensagem: 'Lançamento excluído com sucesso!' });
  } catch (erro) {
    console.error('Erro ao excluir movimentação:', erro);
    return res.status(500).json({ erro: 'Erro interno ao excluir movimentação.' });
  }
});

// ==========================================
// 5. VENCIMENTOS (tabela: vencimentos)
// ==========================================
app.get('/vencimentos', async (req, res) => {
  const { empresa_id } = req.query;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const resultado = await conexao.query(
      'SELECT * FROM vencimentos WHERE empresa_id = $1 ORDER BY data ASC',
      [empresa_id]
    );
    res.json(resultado.rows);
  } catch (erro) {
    console.error('Erro ao buscar vencimentos:', erro);
    res.status(500).json({ erro: 'Erro ao buscar vencimentos' });
  }
});

app.post('/vencimentos', async (req, res) => {
  const { empresa_id, nome, categoria, data, prazo, valor, pago } = req.body;
  if (!empresa_id) {
    return res.status(400).json({ erro: 'empresa_id é obrigatório.' });
  }

  try {
    const query = `
      INSERT INTO vencimentos (empresa_id, nome, categoria, data, prazo, valor, pago)
      VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
    `;
    const resultado = await conexao.query(query, [empresa_id, nome, categoria, data, prazo, valor, pago || false]);
    return res.status(201).json({ mensagem: 'Vencimento salvo com sucesso!', item: resultado.rows[0] });
  } catch (erro) {
    console.error('Erro ao salvar vencimento:', erro);
    return res.status(500).json({ erro: 'Erro ao salvar vencimento' });
  }
});

app.listen(PORT, () => {
  console.log(`Servidor rodando na porta ${PORT}`);
});