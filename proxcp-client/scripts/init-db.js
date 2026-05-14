const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const dbPath = path.resolve(__dirname, '../data/auth.db');
const migrationDir = path.resolve(__dirname, '../better-auth_migrations');

// Ensure data directory exists
const dataDir = path.dirname(dbPath);
if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
}

console.log(`Initializing database at: ${dbPath}`);

const db = new Database(dbPath);

try {
    // 1. Get the latest migration file
    const files = fs.readdirSync(migrationDir)
        .filter(f => f.endsWith('.sql'))
        .sort((a, b) => b.localeCompare(a)); // Get latest by name (timestamp)

    if (files.length === 0) {
        console.log('⚠️ No migration files found. Skipping initialization.');
        process.exit(0);
    }

    const latestMigration = path.join(migrationDir, files[0]);
    console.log(`Reading migration: ${files[0]}`);

    let schema = fs.readFileSync(latestMigration, 'utf8');

    // 2. Add "IF NOT EXISTS" to create table/index statements to prevent errors on restart
    schema = schema.replace(/create table/gi, 'create table if not exists');
    schema = schema.replace(/create index/gi, 'create index if not exists');

    // 3. Execute the schema
    db.exec(schema);
    console.log('✅ Database tables initialized from migration file successfully.');
} catch (error) {
    console.error('❌ Failed to initialize database:', error);
    process.exit(1);
} finally {
    db.close();
}
