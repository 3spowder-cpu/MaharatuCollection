from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Inisialisasi db agar bisa dipanggil di app.py
db = SQLAlchemy()

# --- TABEL PENGGUNA (OWNER & KASIR) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False) 
    role = db.Column(db.String(20), default='kasir') # 'owner' atau 'kasir'
    
    # Relasi
    penjualan_saya = db.relationship('Penjualan', backref='petugas', lazy=True)
    opname_saya = db.relationship('StockOpname', backref='petugas', lazy=True)

class Produk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(20), unique=True)
    stok = db.Column(db.Integer, default=0)
    hpp = db.Column(db.Float, nullable=False) 
    harga_jual = db.Column(db.Float, nullable=False) 
    barcode = db.Column(db.String(100))

# --- TABEL TRANSAKSI ---
class Penjualan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.DateTime, default=datetime.now)
    total_bayar = db.Column(db.Float, nullable=False)
    metode_bayar = db.Column(db.String(50), default="Tunai")
    
    # Mencatat ID User yang melayani transaksi
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    items = db.relationship('ItemPenjualan', backref='induk_penjualan', lazy=True)

class ItemPenjualan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    penjualan_id = db.Column(db.Integer, db.ForeignKey('penjualan.id'), nullable=False)
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False)
    jumlah = db.Column(db.Integer, nullable=False)
    harga_satuan = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

    produk = db.relationship('Produk')

    @property
    def nama_produk(self):
        return self.produk.nama if self.produk else "Produk Tidak Ditemukan"

    @property
    def hpp_produk(self):
        return self.produk.hpp if self.produk else 0

# --- TABEL BARU: STOCK OPNAME ---
class StockOpname(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produk_id = db.Column(db.Integer, db.ForeignKey('produk.id'), nullable=False)
    stok_sistem = db.Column(db.Integer, nullable=False) # Stok menurut aplikasi
    stok_fisik = db.Column(db.Integer, nullable=False)  # Stok hasil hitung manual
    selisih = db.Column(db.Integer, nullable=False)     # Fisik - Sistem
    keterangan = db.Column(db.String(200))              # Alasan selisih
    tanggal = db.Column(db.DateTime, default=datetime.now)
    petugas_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='Pending') # 'Pending' atau 'Approved'

    produk = db.relationship('Produk', backref='riwayat_opname')

class Operasional(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tanggal = db.Column(db.DateTime, default=db.func.current_timestamp())
    kategori = db.Column(db.String(50), nullable=False) # Contoh: Listrik, Gaji, Plastik Packing
    keterangan = db.Column(db.String(200))
    jumlah = db.Column(db.Float, nullable=False)
    petugas_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    petugas = db.relationship('User', backref='biaya_operasional')

class Aset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nama_aset = db.Column(db.String(100), nullable=False)
    jumlah = db.Column(db.Integer, default=1)
    kondisi = db.Column(db.String(50)) # Contoh: Baik, Rusak, Perlu Servis
    lokasi = db.Column(db.String(100)) # Contoh: Gudang, Kasir, Kantor
    tanggal_input = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Aset {self.nama_aset}>'