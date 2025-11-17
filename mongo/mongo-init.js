db = db.getSiblingDB("admin");

// Check if root user exists
var userExists = db.getUser("root");
if (!userExists) {
    db.createUser({
        user: "root",
        pwd: "example",
        roles: [ { role: "root", db: "admin" } ]
    });
} else {
    print("Root user already exists, skipping creation");
}

db.auth("root", "example");

// Switch to app database
db = db.getSiblingDB("appdb");

// Create collection if it does not exist
var collExists = db.getCollectionNames().indexOf("code_entries") >= 0;
if (!collExists) {
    db.createCollection("code_entries", {
        validator: {
            $jsonSchema: {
                bsonType: "object",
                required: ["code_original","code_hash","repo","ingest_timestamp","labels"],
                properties: {
                    code_original: { bsonType: "string" },
                    code_fixed: { bsonType: ["string","null"] },
                    code_hash: { bsonType: "string", pattern: "^[a-fA-F0-9]{64}$" },
                    repo: {
                        bsonType: "object",
                        required: ["url","commit_hash","commit_date"],
                        properties: {
                            url: { bsonType: "string" },
                            commit_hash: { bsonType: "string" },
                            commit_date: { bsonType: "date" }
                        }
                    },
                    ingest_timestamp: { bsonType: "date" },
                    labels: {
                        bsonType: "object",
                        required: ["cppcheck","clang","groups"],
                        properties: {
                            cppcheck: { bsonType: "object" },
                            clang: { bsonType: "object" },
                            groups: {
                                bsonType: "object",
                                properties: {
                                    memory_errors: { enum: [0,1] },
                                    undefined_behavior: { enum: [0,1] },
                                    correctness: { enum: [0,1] },
                                    performance: { enum: [0,1] },
                                    style: { enum: [0,1] }
                                }
                            }
                        }
                    }
                }
            }
        }
    });

    db.code_entries.createIndex({ code_hash: 1 }, { unique: true });
    db.code_entries.createIndex({ "repo.url": 1 });
    db.code_entries.createIndex({ "repo.commit_hash": 1 });
    db.code_entries.createIndex({
        "labels.groups.memory_errors": 1,
        "labels.groups.undefined_behavior": 1
    });
} else {
    print("Collection code_entries already exists, skipping creation");
}
