package main

import (
	"database/sql"
	"flag"
	"fmt"
	"log"
	"os"
	"path/filepath"

	_ "github.com/mattn/go-sqlite3"
)

var (
	dbFilePath string
	limit      int
)

const (
	selectQuery = "SELECT feedurl FROM rss_item GROUP BY feedurl"
	deleteQuery = "DELETE FROM rss_item WHERE feedurl=? AND unread = 0 AND id NOT IN (SELECT id FROM rss_item WHERE feedurl=? ORDER BY pubDate DESC LIMIT ?)"
)

func selectTables() []string {
	db, err := sql.Open("sqlite3", dbFilePath)
	if err != nil {
		log.Fatal(err)
	}
	defer func() { _ = db.Close() }()

	rows, err := db.Query(selectQuery)
	if err != nil {
		log.Fatal(err)
	}
	defer func() { _ = rows.Close() }()

	var tables []string
	for rows.Next() {
		var table string
		if err := rows.Scan(&table); err != nil {
			log.Fatal(err)
		}
		tables = append(tables, table)
	}
	if err := rows.Err(); err != nil {
		log.Fatal(err)
	}

	return tables
}

func cleanDb(tables []string) int {
	db, err := sql.Open("sqlite3", dbFilePath)
	if err != nil {
		log.Fatal(err)
	}
	defer func() { _ = db.Close() }()

	var count int
	for _, t := range tables {
		r, err := db.Exec(deleteQuery, t, t, limit)
		if err != nil {
			log.Fatal(err)
		}
		c, err := r.RowsAffected()
		if err != nil {
			log.Fatal(err)
		}
		count += int(c)
	}
	return count
}

func defaultDbPath() string {
	xdgDataHome := os.Getenv("XDG_DATA_HOME")
	if xdgDataHome == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			log.Fatal(err)
		}
		xdgDataHome = filepath.Join(home, ".local", "share")
	}

	newsboatDataHome := filepath.Join(xdgDataHome, "newsboat")
	if stat, err := os.Stat(newsboatDataHome); err != nil {
		log.Fatal(err)
	} else if !stat.IsDir() {
		log.Fatalf("%s is not dir", newsboatDataHome)
	}
	dbPath := filepath.Join(newsboatDataHome, "cache.db")
	if _, err := os.Stat(dbPath); err != nil {
		log.Fatal(err)
	}
	return dbPath
}

func main() {
	flag.StringVar(&dbFilePath, "d", defaultDbPath(), "db filepath")
	flag.IntVar(&limit, "l", 100, "entries count to leave after deletion for each feed")
	flag.Parse()

	if _, err := os.Stat(dbFilePath); err != nil {
		log.Fatal(err)
	}

	fmt.Print(cleanDb(selectTables()))
}
