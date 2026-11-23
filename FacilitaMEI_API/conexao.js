const { Pool } = require('pg');
require('dotenv').config();

const conexao = new Pool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  port: process.env.DB_PORT || 5432,
  ssl: {
    rejectUnauthorized: false
  }
});

conexao.connect((erro, client, release) => {
  if (erro) {
    console.error('Erro ao conectar ao banco de dados do Supabase:', erro.stack);
    return;
  }
  console.log('Conectado ao PostgreSQL do Supabase com sucesso!');
  release();
});

module.exports = conexao;