CREATE DATABASE IF NOT EXISTS agri_warning
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE agri_warning;

CREATE TABLE IF NOT EXISTS news (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  content TEXT,
  source VARCHAR(100),
  publish_time VARCHAR(50),
  url VARCHAR(500),
  region VARCHAR(100),
  category VARCHAR(50),
  summary TEXT,
  keywords VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_news_url (url),
  KEY idx_news_category (category),
  KEY idx_news_region (region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS product_prices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_name VARCHAR(100) NOT NULL,
  price DECIMAL(10, 2) NOT NULL,
  unit VARCHAR(50),
  region VARCHAR(100),
  province VARCHAR(100),
  city VARCHAR(100),
  market_name VARCHAR(100),
  source_level VARCHAR(50),
  date VARCHAR(50),
  source VARCHAR(100),
  source_url VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_price_item (product_name, region, date, source),
  KEY idx_price_product (product_name),
  KEY idx_price_region (region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS warnings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  region VARCHAR(100),
  product VARCHAR(100),
  risk_type VARCHAR(50),
  risk_score DECIMAL(5, 1),
  risk_level VARCHAR(50),
  keyword_score DECIMAL(5, 1) DEFAULT 0,
  price_score DECIMAL(5, 1) DEFAULT 0,
  heat_score DECIMAL(5, 1) DEFAULT 0,
  region_score DECIMAL(5, 1) DEFAULT 0,
  local_match_score DECIMAL(5, 1) DEFAULT 0,
  source_score DECIMAL(5, 1) DEFAULT 0,
  evidence_score DECIMAL(5, 1) DEFAULT 0,
  confidence DECIMAL(5, 1) DEFAULT 0,
  positive_adjustment DECIMAL(5, 1) DEFAULT 0,
  trigger_words VARCHAR(500),
  evidence_summary VARCHAR(500),
  evidence_links TEXT,
  reason TEXT,
  suggestion TEXT,
  source VARCHAR(100),
  category VARCHAR(50),
  url VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_warning_url_type (url, risk_type),
  KEY idx_warning_level (risk_level),
  KEY idx_warning_region (region),
  KEY idx_warning_product (product)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
