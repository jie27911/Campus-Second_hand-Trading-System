-- ============================================
-- PostgreSQL 校园交易系统初始化脚本 (南校区)
-- ============================================

-- 创建数据库 (如果不存在)
-- 注意: 这个脚本假设数据库已创建

-- 设置字符编码
SET client_encoding = 'UTF8';

-- ============================================
-- 1. 核心业务表 (南校区专用)
-- ============================================

-- 用户表 (从中央同步)
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    student_id VARCHAR(20) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    real_name VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    is_banned BOOLEAN DEFAULT FALSE,
    credit_score INTEGER DEFAULT 100,
    seller_rating DECIMAL(3,2) DEFAULT 5.00,
    buyer_rating DECIMAL(3,2) DEFAULT 5.00,
    total_sales INTEGER DEFAULT 0,
    total_purchases INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

-- 用户资料表
CREATE TABLE IF NOT EXISTS user_profiles (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name VARCHAR(120) NOT NULL,
    phone VARCHAR(32),
    campus VARCHAR(120),
    bio VARCHAR(500),
    avatar_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

-- 商品表 (南校区商品)
CREATE TABLE IF NOT EXISTS items (
    id BIGINT PRIMARY KEY,
    seller_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id BIGINT,
    campus_id BIGINT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    original_price DECIMAL(10,2),
    condition_type VARCHAR(20) DEFAULT '二手',
    location VARCHAR(100),
    contact_info VARCHAR(200),
    tags JSONB,
    status VARCHAR(20) DEFAULT 'available',
    is_negotiable BOOLEAN DEFAULT FALSE,
    is_shipped BOOLEAN DEFAULT FALSE,
    view_count INTEGER DEFAULT 0,
    favorite_count INTEGER DEFAULT 0,
    inquiry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sold_at TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

CREATE INDEX IF NOT EXISTS idx_items_status_category_campus ON items(status, category_id, campus_id);

-- 分类表
CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    icon VARCHAR(100),
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 校区表
CREATE TABLE IF NOT EXISTS campuses (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(20) UNIQUE NOT NULL,
    address VARCHAR(200),
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 商品图片表
CREATE TABLE IF NOT EXISTS item_images (
    id BIGINT PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    image_url VARCHAR(500) NOT NULL,
    sort_order INTEGER DEFAULT 0,
    is_cover BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

-- 购物车表
CREATE TABLE IF NOT EXISTS cart_items (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cart_user_item ON cart_items(user_id, item_id);
CREATE INDEX IF NOT EXISTS idx_cart_user_id ON cart_items(user_id);
CREATE INDEX IF NOT EXISTS idx_cart_item_id ON cart_items(item_id);
CREATE INDEX IF NOT EXISTS idx_cart_created ON cart_items(created_at);

-- 交易表
CREATE TABLE IF NOT EXISTS transactions (
    id BIGINT PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id),
    buyer_id BIGINT NOT NULL REFERENCES users(id),
    seller_id BIGINT NOT NULL REFERENCES users(id),
    item_price DECIMAL(10,2) NOT NULL,
    final_amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    buyer_contact VARCHAR(200),
    seller_contact VARCHAR(200),
    meeting_location VARCHAR(200),
    meeting_time TIMESTAMP,
    buyer_rating SMALLINT,
    seller_rating SMALLINT,
    buyer_review TEXT,
    seller_review TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contacted_at TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

CREATE INDEX IF NOT EXISTS idx_transactions_status_seller_amount ON transactions(status, seller_id, final_amount);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id BIGINT PRIMARY KEY,
    sender_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id BIGINT REFERENCES items(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    is_deleted_by_sender BOOLEAN DEFAULT FALSE,
    is_deleted_by_receiver BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}'
);

-- 收藏表
CREATE TABLE IF NOT EXISTS favorites (
    id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    v_clock TEXT DEFAULT '{"N":0,"S":0}',
    UNIQUE(user_id, item_id)
);

-- ============================================
-- 0. 同步日志表 (Edge) + 哑触发器 (Dumb Triggers)
-- ============================================

-- ============================================
-- v_clock: 本地写入自动递增 (离线也能正确累计版本)
-- 说明:
-- - Postgres 边缘库使用向量时钟键 "S" (South/Branch)
-- - 当 app.sync_suppress='1' (同步复制写入) 时不递增，避免回环/版本漂移
-- ============================================

CREATE OR REPLACE FUNCTION vclock_bump_s()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    vc jsonb;
    cur integer;
BEGIN
    IF current_setting('app.sync_suppress', true) = '1' THEN
        RETURN NEW;
    END IF;

    vc := COALESCE(NULLIF(NEW.v_clock, ''), '{"N":0,"S":0}')::jsonb;
    cur := COALESCE((vc ->> 'S')::integer, 0);
    vc := jsonb_set(vc, '{S}', to_jsonb(cur + 1), true);
    NEW.v_clock := vc::text;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_vclock_users ON users;
CREATE TRIGGER trg_vclock_users
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_user_profiles ON user_profiles;
CREATE TRIGGER trg_vclock_user_profiles
BEFORE INSERT OR UPDATE ON user_profiles
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_items ON items;
CREATE TRIGGER trg_vclock_items
BEFORE INSERT OR UPDATE ON items
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_item_images ON item_images;
CREATE TRIGGER trg_vclock_item_images
BEFORE INSERT OR UPDATE ON item_images
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_transactions ON transactions;
CREATE TRIGGER trg_vclock_transactions
BEFORE INSERT OR UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_messages ON messages;
CREATE TRIGGER trg_vclock_messages
BEFORE INSERT OR UPDATE ON messages
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

DROP TRIGGER IF EXISTS trg_vclock_favorites ON favorites;
CREATE TRIGGER trg_vclock_favorites
BEFORE INSERT OR UPDATE ON favorites
FOR EACH ROW EXECUTE FUNCTION vclock_bump_s();

CREATE TABLE IF NOT EXISTS sync_log (
    log_id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL,
    data_id BIGINT NOT NULL,
    operation VARCHAR(16) NOT NULL,
    old_data JSONB,
    new_data JSONB,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sync_log_status ON sync_log(status, log_id);
CREATE INDEX IF NOT EXISTS idx_sync_log_table_data ON sync_log(table_name, data_id);

CREATE OR REPLACE FUNCTION sync_log_capture() RETURNS trigger AS $$
BEGIN
    IF current_setting('app.sync_suppress', true) = '1' THEN
        IF (TG_OP = 'DELETE') THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;

    IF (TG_OP = 'INSERT') THEN
        INSERT INTO sync_log(table_name, data_id, operation, old_data, new_data)
        VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', NULL, to_jsonb(NEW));
        RETURN NEW;
    ELSIF (TG_OP = 'UPDATE') THEN
        INSERT INTO sync_log(table_name, data_id, operation, old_data, new_data)
        VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW));
        RETURN NEW;
    ELSIF (TG_OP = 'DELETE') THEN
        INSERT INTO sync_log(table_name, data_id, operation, old_data, new_data)
        VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', to_jsonb(OLD), NULL);
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_users ON users;
CREATE TRIGGER trg_sync_users
AFTER INSERT OR UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_user_profiles ON user_profiles;
CREATE TRIGGER trg_sync_user_profiles
AFTER INSERT OR UPDATE OR DELETE ON user_profiles
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_items ON items;
CREATE TRIGGER trg_sync_items
AFTER INSERT OR UPDATE OR DELETE ON items
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_item_images ON item_images;
CREATE TRIGGER trg_sync_item_images
AFTER INSERT OR UPDATE OR DELETE ON item_images
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_transactions ON transactions;
CREATE TRIGGER trg_sync_transactions
AFTER INSERT OR UPDATE OR DELETE ON transactions
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_messages ON messages;
CREATE TRIGGER trg_sync_messages
AFTER INSERT OR UPDATE OR DELETE ON messages
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

DROP TRIGGER IF EXISTS trg_sync_favorites ON favorites;
CREATE TRIGGER trg_sync_favorites
AFTER INSERT OR UPDATE OR DELETE ON favorites
FOR EACH ROW EXECUTE FUNCTION sync_log_capture();

-- ============================================
-- 1. 业务维护触发器 (与 MySQL/MariaDB 保持一致)
-- 说明: 这些触发器不受 app.sync_suppress 影响，用于维护派生字段
-- ============================================

CREATE OR REPLACE FUNCTION fn_before_item_view_update() RETURNS trigger AS $$
BEGIN
    IF NEW.view_count IS DISTINCT FROM OLD.view_count THEN
        NEW.updated_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_before_item_view_update ON items;
CREATE TRIGGER trg_before_item_view_update
BEFORE UPDATE ON items
FOR EACH ROW EXECUTE FUNCTION fn_before_item_view_update();

CREATE OR REPLACE FUNCTION fn_after_favorite_insert() RETURNS trigger AS $$
BEGIN
    UPDATE items SET favorite_count = favorite_count + 1 WHERE id = NEW.item_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_favorite_insert ON favorites;
CREATE TRIGGER trg_after_favorite_insert
AFTER INSERT ON favorites
FOR EACH ROW EXECUTE FUNCTION fn_after_favorite_insert();

CREATE OR REPLACE FUNCTION fn_after_favorite_delete() RETURNS trigger AS $$
BEGIN
    UPDATE items SET favorite_count = GREATEST(favorite_count - 1, 0) WHERE id = OLD.item_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_favorite_delete ON favorites;
CREATE TRIGGER trg_after_favorite_delete
AFTER DELETE ON favorites
FOR EACH ROW EXECUTE FUNCTION fn_after_favorite_delete();

CREATE OR REPLACE FUNCTION fn_after_transaction_complete() RETURNS trigger AS $$
BEGIN
    IF NEW.status = 'completed' AND (OLD.status IS DISTINCT FROM 'completed') THEN
        UPDATE users SET total_sales = total_sales + 1 WHERE id = NEW.seller_id;
        UPDATE users SET total_purchases = total_purchases + 1 WHERE id = NEW.buyer_id;
        UPDATE items SET status = 'sold', sold_at = NOW() WHERE id = NEW.item_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_transaction_complete ON transactions;
CREATE TRIGGER trg_after_transaction_complete
AFTER UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION fn_after_transaction_complete();

CREATE OR REPLACE FUNCTION fn_after_transaction_rating() RETURNS trigger AS $$
BEGIN
    IF NEW.seller_rating IS NOT NULL AND OLD.seller_rating IS NULL THEN
        UPDATE users
        SET seller_rating = (
            SELECT AVG(seller_rating)::double precision
            FROM transactions
            WHERE seller_id = NEW.seller_id AND seller_rating IS NOT NULL
        )
        WHERE id = NEW.seller_id;
    END IF;

    IF NEW.buyer_rating IS NOT NULL AND OLD.buyer_rating IS NULL THEN
        UPDATE users
        SET buyer_rating = (
            SELECT AVG(buyer_rating)::double precision
            FROM transactions
            WHERE buyer_id = NEW.buyer_id AND buyer_rating IS NOT NULL
        )
        WHERE id = NEW.buyer_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_transaction_rating ON transactions;
CREATE TRIGGER trg_after_transaction_rating
AFTER UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION fn_after_transaction_rating();

-- 系统配置表

-- 用户关注表
CREATE TABLE IF NOT EXISTS user_follows (
    id BIGSERIAL PRIMARY KEY,
    follower_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    following_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0,
    UNIQUE(follower_id, following_id)
);

-- 商品浏览历史表
CREATE TABLE IF NOT EXISTS item_view_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    view_duration INTEGER DEFAULT 0,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 用户地址表
CREATE TABLE IF NOT EXISTS user_addresses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    address_type VARCHAR(20) DEFAULT 'dormitory',
    building VARCHAR(50),
    room VARCHAR(20),
    detail_address VARCHAR(200),
    contact_name VARCHAR(50),
    contact_phone VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 商品价格历史表
CREATE TABLE IF NOT EXISTS item_price_history (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    old_price DECIMAL(10,2),
    new_price DECIMAL(10,2) NOT NULL,
    change_reason VARCHAR(200),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 消息附件表
CREATE TABLE IF NOT EXISTS message_attachments (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    file_type VARCHAR(20) DEFAULT 'image',
    file_url VARCHAR(500) NOT NULL,
    file_name VARCHAR(200),
    file_size BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 交易评价图片表
CREATE TABLE IF NOT EXISTS transaction_review_images (
    id BIGSERIAL PRIMARY KEY,
    transaction_id BIGINT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    reviewer_type VARCHAR(20) NOT NULL,
    image_url VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 系统通知表
CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    related_id BIGINT,
    related_type VARCHAR(50),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 0
);

-- 搜索历史表
CREATE TABLE IF NOT EXISTS search_history (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    keyword VARCHAR(200) NOT NULL,
    result_count INTEGER DEFAULT 0,
    clicked_item_id BIGINT REFERENCES items(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 数据库同步任务表

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_items_seller_id ON items(seller_id);
CREATE INDEX IF NOT EXISTS idx_items_category_id ON items(category_id);
CREATE INDEX IF NOT EXISTS idx_items_campus_id ON items(campus_id);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_item_images_item_id ON item_images(item_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_receiver_id ON messages(receiver_id);
CREATE INDEX IF NOT EXISTS idx_transactions_buyer_id ON transactions(buyer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_seller_id ON transactions(seller_id);
CREATE INDEX IF NOT EXISTS idx_transactions_item_id ON transactions(item_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_item_id ON favorites(item_id);
CREATE INDEX IF NOT EXISTS idx_user_follows_follower_id ON user_follows(follower_id);
CREATE INDEX IF NOT EXISTS idx_user_follows_following_id ON user_follows(following_id);
CREATE INDEX IF NOT EXISTS idx_item_view_history_user_id ON item_view_history(user_id);
CREATE INDEX IF NOT EXISTS idx_item_view_history_item_id ON item_view_history(item_id);
CREATE INDEX IF NOT EXISTS idx_search_history_user_id ON search_history(user_id);

-- 插入默认校区数据（支持 docker compose down -v 后重建仍保留）
INSERT INTO campuses (id, name, code, address, description, is_active, sort_order, sync_version) VALUES
(2, '南校区', 'south', NULL, '南校区', true, 1, 1)
ON CONFLICT (id) DO NOTHING;

-- 插入默认分类
INSERT INTO categories (name, slug, description, sort_order, is_active, sync_version) VALUES
('全部', 'all', '所有商品', 0, true, 1),
('数码产品', 'electronics', '电脑、手机、平板等', 1, true, 1),
('图书教材', 'books', '教材、课外书、杂志等', 2, true, 1),
('生活用品', 'daily', '日用品、家居用品', 3, true, 1),
('运动装备', 'sports', '运动器材、健身用品', 4, true, 1),
('服装鞋包', 'fashion', '衣服、鞋子、包包', 5, true, 1),
('美妆护肤', 'beauty', '化妆品、护肤品', 6, true, 1),
('票券卡劵', 'tickets', '优惠券、会员卡等', 7, true, 1),
('其他', 'other', '其他商品', 99, true, 1)
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name,
    description = EXCLUDED.description,
    sort_order = EXCLUDED.sort_order,
    is_active = EXCLUDED.is_active,
    sync_version = EXCLUDED.sync_version;

-- ============================================
-- 2. RBAC 权限管理表
-- ============================================

-- 角色表 (RBAC)
CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1
);

-- 权限表 (RBAC)
CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    resource VARCHAR(50) NOT NULL,
    action VARCHAR(50) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1
);

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1,
    UNIQUE(user_id, role_id)
);

-- 角色权限关联表
CREATE TABLE IF NOT EXISTS role_permissions (
    id BIGSERIAL PRIMARY KEY,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1,
    UNIQUE(role_id, permission_id)
);

-- ============================================
-- 3. 初始化RBAC数据
-- ============================================

-- 插入默认角色
INSERT INTO roles (name, description, sync_version) VALUES
('admin', '系统管理员', 1),
('moderator', '内容审核员', 1),
('user', '普通用户', 1),
('seller', '认证卖家', 1)
ON CONFLICT (name) DO NOTHING;

-- 插入默认权限
INSERT INTO permissions (name, resource, action, description, sync_version) VALUES
('user:read', 'user', 'read', '查看用户信息', 1),
('user:write', 'user', 'write', '修改用户信息', 1),
('user:delete', 'user', 'delete', '删除用户', 1),
('item:read', 'item', 'read', '查看商品', 1),
('item:write', 'item', 'write', '发布/修改商品', 1),
('item:delete', 'item', 'delete', '删除商品', 1),
('order:read', 'order', 'read', '查看订单', 1),
('order:write', 'order', 'write', '创建/修改订单', 1),
('admin:access', 'admin', 'access', '访问管理后台', 1),
('report:handle', 'report', 'handle', '处理举报', 1)
ON CONFLICT (name) DO NOTHING;

-- 角色权限关联
INSERT INTO role_permissions (role_id, permission_id, sync_version) VALUES
-- admin 拥有所有权限
(1, 1, 1), (1, 2, 1), (1, 3, 1), (1, 4, 1), (1, 5, 1), (1, 6, 1), (1, 7, 1), (1, 8, 1), (1, 9, 1), (1, 10, 1),
-- moderator 拥有审核权限
(2, 1, 1), (2, 4, 1), (2, 6, 1), (2, 7, 1), (2, 9, 1), (2, 10, 1),
-- user 拥有基本权限
(3, 1, 1), (3, 4, 1), (3, 5, 1), (3, 7, 1), (3, 8, 1),
-- seller 拥有卖家权限
(4, 1, 1), (4, 4, 1), (4, 5, 1), (4, 6, 1), (4, 7, 1), (4, 8, 1)
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- 创建管理员用户 (如果不存在)
INSERT INTO users (
    id, username, email, password_hash, is_active, is_verified, credit_score, sync_version
) VALUES (
    9999,
    'admin',
    'admin@campus.edu',
    '$2b$12$KLysJ85PhtqHTQGptnrr6.c1yOdB51s1j65u8dsOPtiVssLJKi/De',
    TRUE,
    TRUE,
    100,
    1
) ON CONFLICT DO NOTHING;

-- 默认系统配置
-- 为管理员用户分配admin角色
INSERT INTO user_roles (user_id, role_id, sync_version)
SELECT u.id, r.id, 1
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;
