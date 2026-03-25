from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash, send_file
from models import db, Produk, Penjualan, ItemPenjualan, User, StockOpname, Operasional, Aset
from datetime import datetime
from functools import wraps
from sqlalchemy import func
import pandas as pd
from io import BytesIO

app = Flask(__name__)

# Konfigurasi Database & Security
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///toko_kita.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'maharatu_secret_key_123'

db.init_app(app)

# ------------------------------------------------------------------
# DEKORATOR PROTEKSI (Cek Login & Role)
# ------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def owner_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'owner':
            return "Akses Ditolak! Menu ini hanya untuk Owner.", 403
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------------------------------------------
# 1. AUTHENTICATION (LOGIN/LOGOUT)
# ------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            return redirect(url_for('home'))
        return "Username atau Password salah!", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ------------------------------------------------------------------
# 2. ROUTE DASHBOARD
# ------------------------------------------------------------------
@app.route('/')
@login_required
def home():
    total_stok_pcs = db.session.query(db.func.sum(Produk.stok)).scalar() or 0
    total_produk_unik = Produk.query.count()
    
    total_nilai_inventori = 0
    laba_kotor = 0
    total_operasional = 0

    # Ambil Total Operasional secara aman
    try:
        total_operasional = db.session.query(db.func.sum(Operasional.jumlah)).scalar() or 0
    except Exception as e:
        print(f"Error hitung operasional: {e}")

    if session.get('role') == 'owner':
        total_nilai_inventori = sum(p.stok * p.hpp for p in Produk.query.all())
        semua_item_terjual = ItemPenjualan.query.all()
        for item in semua_item_terjual:
            if item.produk:
                untung_per_item = (item.harga_satuan - item.produk.hpp) * item.jumlah
                laba_kotor += untung_per_item

    laba_bersih = laba_kotor - total_operasional
    omzet = db.session.query(db.func.sum(Penjualan.total_bayar)).scalar() or 0
    total_terjual = db.session.query(db.func.sum(ItemPenjualan.jumlah)).scalar() or 0

    query_terlaris = db.session.query(
        Produk.nama, 
        db.func.sum(ItemPenjualan.jumlah).label('total')
    ).join(ItemPenjualan).group_by(Produk.id).order_by(db.func.sum(ItemPenjualan.jumlah).desc()).limit(5).all()

    stok_tipis = Produk.query.filter(Produk.stok <= 5).all()

    return render_template('dashboard.html', 
                           total_stok=total_stok_pcs, 
                           total_produk=total_produk_unik,
                           nilai_inventori=total_nilai_inventori,
                           total_omzet=omzet,
                           total_terjual=total_terjual,
                           laba_kotor=laba_kotor,
                           total_operasional=total_operasional,
                           laba_bersih=laba_bersih, 
                           terlaris=query_terlaris, 
                           stok_tipis=stok_tipis)

# ------------------------------------------------------------------
# 3. ROUTE INVENTORI (Owner Only)
# ------------------------------------------------------------------
@app.route('/admin/inventori')
@login_required
@owner_only
def inventori():
    daftar_produk = Produk.query.all()
    return render_template('inventori.html', produk=daftar_produk)

@app.route('/tambah_produk', methods=['POST'])
@login_required
@owner_only
def tambah_produk():
    sku = request.form.get('sku')
    produk_ada = Produk.query.filter_by(sku=sku).first()
    if produk_ada:
        flash(f'Gagal! SKU "{sku}" sudah digunakan oleh produk: {produk_ada.nama}', 'danger')
        return redirect(url_for('inventori'))

    try:
        produk_baru = Produk(
            barcode=request.form.get('barcode'),
            nama=request.form.get('nama'),
            sku=sku,
            stok=int(request.form.get('stok')),
            hpp=float(request.form.get('hpp')),
            harga_jual=float(request.form.get('harga_jual'))
        )
        db.session.add(produk_baru)
        db.session.commit()
        flash('Produk berhasil ditambahkan!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Terjadi kesalahan sistem saat menyimpan data.', 'danger')
    return redirect(url_for('inventori'))

@app.route('/edit_produk/<int:id>', methods=['POST'])
@login_required
@owner_only
def edit_produk(id):
    p = Produk.query.get_or_404(id)
    p.barcode = request.form.get('barcode')
    p.nama = request.form.get('nama')
    p.sku = request.form.get('sku')
    p.stok = int(request.form.get('stok'))
    p.hpp = float(request.form.get('hpp'))
    p.harga_jual = float(request.form.get('harga_jual'))
    db.session.commit()
    return redirect(url_for('inventori'))

@app.route('/hapus_produk/<int:id>')
@login_required
@owner_only
def hapus_produk(id):
    db.session.delete(Produk.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('inventori'))

# ------------------------------------------------------------------
# 4. ROUTE KASIR & TRANSAKSI
# ------------------------------------------------------------------
@app.route('/kasir')
@login_required
def kasir():
    return render_template('kasir.html')

@app.route('/api/get_produk/<barcode>')
@login_required
def get_produk(barcode):
    p = Produk.query.filter_by(barcode=barcode).first()
    if p:
        return jsonify({"id": p.id, "nama": p.nama, "harga": p.harga_jual, "stok": p.stok})
    return jsonify({"error": "Produk tidak ditemukan"}), 404

@app.route('/proses_transaksi', methods=['POST'])
@login_required
def proses_transaksi():
    data = request.json
    try:
        total_bayar = sum(item['subtotal'] for item in data['items'])
        penjualan_baru = Penjualan(total_bayar=total_bayar, user_id=session.get('user_id'))
        db.session.add(penjualan_baru)
        db.session.flush() 
        
        for item in data['items']:
            produk = Produk.query.get(item['id'])
            if produk:
                if produk.stok < item['qty']:
                    db.session.rollback()
                    return jsonify({"error": f"Stok {produk.nama} tidak mencukupi!"}), 400
                
                detail = ItemPenjualan(
                    penjualan_id=penjualan_baru.id,
                    produk_id=produk.id,
                    jumlah=item['qty'],
                    harga_satuan=item['harga'],
                    subtotal=item['subtotal']
                )
                produk.stok -= item['qty']
                db.session.add(detail)
                db.session.add(produk)
        
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------------
# 5. ROUTE STOCK OPNAME
# ------------------------------------------------------------------
@app.route('/opname', methods=['GET', 'POST'])
@login_required
def opname():
    if request.method == 'POST':
        p_id = request.form.get('produk_id')
        fisik = int(request.form.get('stok_fisik'))
        produk = Produk.query.get(p_id)
        selisih = fisik - produk.stok
        
        laporan_baru = StockOpname(
            produk_id=p_id,
            stok_sistem=produk.stok,
            stok_fisik=fisik,
            selisih=selisih,
            keterangan=request.form.get('keterangan'),
            petugas_id=session['user_id']
        )
        db.session.add(laporan_baru)
        db.session.commit()
        return redirect(url_for('opname'))

    filter_date = request.args.get('filter_date')
    produk_list = Produk.query.all()
    query = StockOpname.query
    if filter_date:
        query = query.filter(func.date(StockOpname.tanggal) == filter_date)
    riwayat = query.order_by(StockOpname.id.desc()).all()
    return render_template('opname.html', produk=produk_list, riwayat=riwayat, filter_date=filter_date)

@app.route('/approve_opname/<int:id>')
@login_required
@owner_only
def approve_opname(id):
    op = StockOpname.query.get_or_404(id)
    if op.status == 'Pending':
        produk = Produk.query.get(op.produk_id)
        produk.stok = op.stok_fisik 
        op.status = 'Approved'
        db.session.commit()
    return redirect(url_for('opname'))

# ------------------------------------------------------------------
# 6. ROUTE LAPORAN & DOWNLOAD EXCEL
# ------------------------------------------------------------------
@app.route('/admin/laporan')
@login_required
def laporan():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    user_filter = request.args.get('user_id')
    
    query = Penjualan.query.order_by(Penjualan.id.desc())
    if start_date and end_date:
        query = query.filter(Penjualan.tanggal.between(start_date, end_date))
    
    if user_filter and user_filter != 'semua':
        query = query.filter_by(user_id=int(user_filter))
    
    penjualan = query.all()
    total_omzet = sum(j.total_bayar for j in penjualan)
    daftar_user = User.query.all()
    
    return render_template('laporan.html', 
                            penjualan=penjualan, 
                            total_omzet=total_omzet, 
                            sd=start_date, 
                            ed=end_date,
                            users=daftar_user,
                            selected_user=user_filter)

@app.route('/admin/download-laporan')
@login_required
@owner_only
def download_laporan():
    penjualan_data = Penjualan.query.all()
    export_data = []
    for p in penjualan_data:
        nama_petugas = "N/A"
        if hasattr(p, 'user') and p.user:
            nama_petugas = p.user.username
        elif hasattr(p, 'user_id'):
            u = User.query.get(p.user_id)
            if u: nama_petugas = u.username

        export_data.append({
            "ID Transaksi": p.id,
            "Tanggal": p.tanggal.strftime('%Y-%m-%d %H:%M') if p.tanggal else "N/A",
            "Total Bayar": p.total_bayar,
            "Petugas": nama_petugas
        })
    
    df = pd.DataFrame(export_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Laporan Penjualan')
    
    output.seek(0)
    filename = f"Laporan_Maharatu_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/admin/hapus-penjualan/<int:id>', methods=['POST'])
@login_required
@owner_only
def hapus_penjualan(id):
    transaksi = Penjualan.query.get_or_404(id)
    try:
        for item in transaksi.items:
            produk = Produk.query.get(item.produk_id)
            if produk:
                produk.stok += item.jumlah
        ItemPenjualan.query.filter_by(penjualan_id=id).delete()
        db.session.delete(transaksi)
        db.session.commit()
        return redirect('/admin/laporan')
    except Exception as e:
        db.session.rollback()
        return f"Gagal menghapus transaksi: {str(e)}"

# ------------------------------------------------------------------
# 7. KELOLA KARYAWAN
# ------------------------------------------------------------------
@app.route('/admin/karyawan')
@login_required
@owner_only
def kelola_karyawan():
    semua_user = User.query.all()
    return render_template('karyawan.html', users=semua_user)

@app.route('/tambah_karyawan', methods=['POST'])
@login_required
@owner_only
def tambah_karyawan():
    user_baru = User(
        username=request.form.get('username'),
        password=request.form.get('password'),
        role=request.form.get('role')
    )
    db.session.add(user_baru)
    db.session.commit()
    return redirect(url_for('kelola_karyawan'))

@app.route('/hapus_user/<int:id>')
@login_required
@owner_only
def hapus_user(id):
    if id == session.get('user_id'):
        return "Anda tidak bisa menghapus akun sendiri!", 400
    db.session.delete(User.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('kelola_karyawan'))

# ------------------------------------------------------------------
# 8. LAIN-LAIN
# ------------------------------------------------------------------
@app.route('/admin/cetak_barcode')
def cetak_barcode():
    if session.get('role') != 'owner': return "Akses Ditolak", 403
    semua_produk = Produk.query.all()
    return render_template('cetak_barcode.html', produk=semua_produk)

# ------------------------------------------------------------------
# 9. ROUTE OPERASIONAL (Diubah nama fungsi agar tidak bentrok model)
# ------------------------------------------------------------------
@app.route('/operasional', methods=['GET', 'POST'])
@login_required
def halaman_operasional():
    if request.method == 'POST':
        try:
            baru = Operasional(
                kategori=request.form.get('kategori'),
                jumlah=float(request.form.get('jumlah')),
                keterangan=request.form.get('keterangan'),
                petugas_id=session.get('user_id')
            )
            db.session.add(baru)
            db.session.commit()
            flash('Biaya operasional berhasil dicatat!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal mencatat biaya: {str(e)}', 'danger')
        return redirect(url_for('halaman_operasional'))

    daftar_biaya = Operasional.query.order_by(Operasional.tanggal.desc()).all()
    total_biaya = sum(b.jumlah for b in daftar_biaya)
    return render_template('operasional.html', biaya=daftar_biaya, total=total_biaya)

@app.route('/operasional/edit/<int:id>', methods=['POST'])
@login_required
@owner_only
def edit_operasional(id):
    biaya = Operasional.query.get_or_404(id)
    biaya.kategori = request.form.get('kategori')
    biaya.jumlah = float(request.form.get('jumlah'))
    biaya.keterangan = request.form.get('keterangan')
    db.session.commit()
    flash('Data operasional diperbarui!', 'success')
    return redirect(url_for('halaman_operasional'))

@app.route('/operasional/hapus/<int:id>')
@login_required
@owner_only
def hapus_operasional(id):
    biaya = Operasional.query.get_or_404(id)
    db.session.delete(biaya)
    db.session.commit()
    flash('Data operasional dihapus!', 'warning')
    return redirect(url_for('halaman_operasional'))

# ------------------------------------------------------------------
# 10. MANAJEMEN ASET
# ------------------------------------------------------------------
@app.route('/admin/aset', methods=['GET', 'POST'])
@login_required
@owner_only
def kelola_aset():
    if request.method == 'POST':
        aset_baru = Aset(
            nama_aset=request.form.get('nama_aset'),
            jumlah=int(request.form.get('jumlah')),
            kondisi=request.form.get('kondisi'),
            lokasi=request.form.get('lokasi')
        )
        db.session.add(aset_baru)
        db.session.commit()
        flash('Aset berhasil dicatat!', 'success')
        return redirect(url_for('kelola_aset'))

    daftar_aset = Aset.query.all()
    return render_template('aset.html', aset=daftar_aset)

@app.route('/admin/aset/edit/<int:id>', methods=['POST'])
@login_required
@owner_only
def edit_aset(id):
    a = Aset.query.get_or_404(id)
    a.nama_aset = request.form.get('nama_aset')
    a.jumlah = int(request.form.get('jumlah'))
    a.kondisi = request.form.get('kondisi')
    a.lokasi = request.form.get('lokasi')
    db.session.commit()
    return redirect(url_for('kelola_aset'))

@app.route('/admin/aset/hapus/<int:id>')
@login_required
@owner_only
def hapus_aset(id):
    a = Aset.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for('kelola_aset'))

# ------------------------------------------------------------------
# MAIN PROGRAM
# ------------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', password='123', role='owner')
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)