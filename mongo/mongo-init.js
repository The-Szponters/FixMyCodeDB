// ==========================================
// CONFIGURATION
// ==========================================
var CONFIG = {
    ADMIN_DB: "admin",
    APP_DB: "appdb",
    ROOT_USER: "root",
    ROOT_PASS: "example",
    COLL_NAME: "code_entries"
};

// ==========================================
// 1. ADMIN & AUTHENTICATION
// ==========================================
print("--- Starting Database Initialization ---");

db = db.getSiblingDB(CONFIG.ADMIN_DB);

try {
    var user = db.getUser(CONFIG.ROOT_USER);
    if (!user) {
        print(`Creating user: ${CONFIG.ROOT_USER}`);
        db.createUser({
            user: CONFIG.ROOT_USER,
            pwd: CONFIG.ROOT_PASS,
            roles: [{ role: "root", db: CONFIG.ADMIN_DB }]
        });
    } else {
        print(`User ${CONFIG.ROOT_USER} already exists. Skipping creation.`);
    }

    db.auth(CONFIG.ROOT_USER, CONFIG.ROOT_PASS);

} catch (e) {
    print("Error during user setup: " + e);
}

// ==========================================
// 2. SCHEMA DEFINITION
// ==========================================

var schemaValidator = {
    $jsonSchema: {
        bsonType: "object",
        required: ["code_original", "code_hash", "repo", "ingest_timestamp", "labels"],
        properties: {
            // Scraper stores code as strings in DB payload
            // Accept both shapes.
            code_original: { bsonType: ["string", "array"], items: { bsonType: "string" } },
            code_fixed: { bsonType: ["string", "array", "null"], items: { bsonType: "string" } },
            // Enforce SHA-256 Hex string format
            code_hash: { bsonType: "string", pattern: "^[a-fA-F0-9]{64}$" },
            repo: {
                bsonType: "object",
                required: ["url", "commit_hash", "commit_date"],
                properties: {
                    url: { bsonType: "string" },
                    commit_hash: { bsonType: "string" },
                    commit_date: { bsonType: "date" }
                }
            },
            ingest_timestamp: { bsonType: "date" },
            labels: {
                bsonType: "object",
                required: ["cppcheck", "clang", "groups"],
                properties: {
                    // Labeler returns a list of issue IDs (strings).
                    cppcheck: { bsonType: "array", items: { bsonType: "string" } },
                    clang: { bsonType: "object" },
                    groups: {
                        bsonType: "object",
                        properties: {
                            // Keys follow scraper/labels_config.json and scraper/labeling/labeler.py
                            memory_management: { bsonType: "bool" },
                            invalid_access: { bsonType: "bool" },
                            uninitialized: { bsonType: "bool" },
                            concurrency: { bsonType: "bool" },
                            logic_error: { bsonType: "bool" },
                            resource_leak: { bsonType: "bool" },
                            security_portability: { bsonType: "bool" },
                            code_quality_performance: { bsonType: "bool" }
                        }
                    }
                }
            }
        }
    }
};

// ==========================================
// 3. COLLECTION SETUP (UPSERT LOGIC)
// ==========================================

db = db.getSiblingDB(CONFIG.APP_DB);

var collExists = db.getCollectionNames().indexOf(CONFIG.COLL_NAME) >= 0;

if (!collExists) {
    print(`Collection '${CONFIG.COLL_NAME}' does not exist. Creating...`);
    db.createCollection(CONFIG.COLL_NAME, {
        validator: schemaValidator
    });
} else {
    print(`Collection '${CONFIG.COLL_NAME}' exists. Updating Schema Validator...`);
    db.runCommand({
        collMod: CONFIG.COLL_NAME,
        validator: schemaValidator
    });
}

// ==========================================
// 4. INDEXING
// ==========================================
print("Ensuring Indexes...");

var coll = db.getCollection(CONFIG.COLL_NAME);

coll.createIndex({ code_hash: 1 }, { unique: true });

coll.createIndex({ "repo.url": 1 });
coll.createIndex({ "repo.commit_hash": 1 });

print("--- Initialization Complete ---");