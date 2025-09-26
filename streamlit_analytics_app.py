import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from collections import Counter
import time

# Configuration de la page
st.set_page_config(
    page_title="Analytics Sneakers",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration des secrets Streamlit
NOTION_API_KEY = st.secrets["NOTION_API_KEY"]
SALES_DB_ID = st.secrets["SALES_DB_ID"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK"]

# Cache pour éviter trop d'appels API
@st.cache_data(ttl=300)  # Cache 5 minutes
def get_sales_data():
    """Récupère les données de vente depuis Notion"""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    
    all_results = []
    has_more = True
    next_cursor = None
    
    url = f"https://api.notion.com/v1/databases/{SALES_DB_ID}/query"
    
    while has_more:
        data = {}
        if next_cursor:
            data["start_cursor"] = next_cursor
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            st.error(f"Erreur API Notion: {response.status_code}")
            return []
        
        result = response.json()
        all_results.extend(result.get("results", []))
        has_more = result.get("has_more", False)
        next_cursor = result.get("next_cursor")
    
    return all_results

def extract_sale_data(page):
    """Extrait les données d'une vente"""
    props = page["properties"]
    
    # Titre
    try:
        title = props["Sneakers Nom"]["title"][0]["text"]["content"]
    except:
        title = "Produit sans nom"
    
    # Prix de vente
    try:
        sell_price = props["Prix de Vente"]["number"]
    except:
        sell_price = 0
    
    # Prix d'achat
    try:
        buy_price = props["Prix d'Achat"]["number"]
    except:
        buy_price = 0
    
    # Date de vente
    try:
        sale_date = props["Date de Vente"]["date"]["start"]
        sale_date = datetime.strptime(sale_date, "%Y-%m-%d").date()
    except:
        sale_date = None
    
    return {
        "title": title,
        "sell_price": sell_price or 0,
        "buy_price": buy_price or 0,
        "margin": (sell_price or 0) - (buy_price or 0),
        "sale_date": sale_date
    }

def send_discord_notification(message):
    """Envoie notification Discord"""
    try:
        payload = {
            "embeds": [{
                "title": "📊 Analytics Dashboard",
                "description": message,
                "color": 0x0099ff,
                "timestamp": datetime.now().isoformat()
            }]
        }
        requests.post(DISCORD_WEBHOOK, json=payload)
        return True
    except:
        return False

# Interface principale
def main():
    st.title("📊 Analytics Sneakers Dashboard")
    st.markdown("---")
    
    # Sidebar
    st.sidebar.title("⚙️ Contrôles")
    
    if st.sidebar.button("🔄 Actualiser données", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    if st.sidebar.button("📤 Envoyer résumé Discord"):
        # On calculera et enverra le résumé
        pass
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("🔄 Auto-refresh (30s)", value=True)
    if auto_refresh:
        placeholder = st.sidebar.empty()
        countdown = st.sidebar.progress(0)
        
    # Récupération des données
    with st.spinner("Chargement des données..."):
        raw_data = get_sales_data()
    
    if not raw_data:
        st.error("Aucune donnée trouvée")
        return
    
    # Traitement des données
    sales_data = []
    for page in raw_data:
        sale = extract_sale_data(page)
        if sale["sale_date"]:  # Seulement les ventes avec date
            sales_data.append(sale)
    
    df = pd.DataFrame(sales_data)
    
    if df.empty:
        st.warning("Aucune vente trouvée")
        return
    
    # Calculs des périodes
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    
    # Filtrage par période
    df_today = df[df['sale_date'] == today]
    df_week = df[df['sale_date'] >= week_start]
    df_month = df[df['sale_date'] >= month_start]
    
    # Métriques principales
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "📅 Aujourd'hui",
            f"{len(df_today)} ventes",
            f"{df_today['sell_price'].sum():.0f} € CA"
        )
    
    with col2:
        st.metric(
            "📊 Cette semaine", 
            f"{len(df_week)} ventes",
            f"{df_week['sell_price'].sum():.0f} € CA"
        )
    
    with col3:
        st.metric(
            "📈 Ce mois",
            f"{len(df_month)} ventes", 
            f"{df_month['sell_price'].sum():.0f} € CA"
        )
    
    with col4:
        marge_mois = df_month['margin'].sum()
        taux_marge = (marge_mois / df_month['sell_price'].sum() * 100) if df_month['sell_price'].sum() > 0 else 0
        st.metric(
            "💰 Marge mois",
            f"{marge_mois:.0f} €",
            f"{taux_marge:.1f}%"
        )
    
    # Graphiques
    st.markdown("---")
    
    # Ventes par jour (30 derniers jours)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Ventes par jour (30j)")
        
        # Préparer les données des 30 derniers jours
        date_range = pd.date_range(end=today, periods=30, freq='D')
        daily_sales = df.groupby('sale_date').size().reindex(
            [d.date() for d in date_range], fill_value=0
        )
        
        fig_daily = px.bar(
            x=daily_sales.index,
            y=daily_sales.values,
            title="Nombre de ventes par jour"
        )
        fig_daily.update_layout(height=400)
        st.plotly_chart(fig_daily, use_container_width=True)
    
    with col2:
        st.subheader("💰 CA par semaine")
        
        # CA par semaine (12 dernières semaines)
        df['week'] = df['sale_date'].apply(lambda x: x - timedelta(days=x.weekday()))
        weekly_ca = df.groupby('week')['sell_price'].sum().tail(12)
        
        fig_weekly = px.line(
            x=weekly_ca.index,
            y=weekly_ca.values,
            title="Chiffre d'affaires hebdomadaire"
        )
        fig_weekly.update_layout(height=400)
        st.plotly_chart(fig_weekly, use_container_width=True)
    
    # Top produits et données détaillées
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏆 Top 10 Produits")
        top_products = Counter(df['title']).most_common(10)
        
        if top_products:
            top_df = pd.DataFrame(top_products, columns=['Produit', 'Ventes'])
            
            fig_top = px.bar(
                top_df,
                x='Ventes',
                y='Produit',
                orientation='h',
                title="Produits les plus vendus"
            )
            fig_top.update_layout(height=500)
            st.plotly_chart(fig_top, use_container_width=True)
        else:
            st.info("Aucun produit vendu")
    
    with col2:
        st.subheader("📊 Statistiques détaillées")
        
        # Stats par période dans un tableau
        stats_data = {
            "Période": ["Aujourd'hui", "Cette semaine", "Ce mois", "Total"],
            "Ventes": [
                len(df_today),
                len(df_week), 
                len(df_month),
                len(df)
            ],
            "CA (€)": [
                f"{df_today['sell_price'].sum():.0f}",
                f"{df_week['sell_price'].sum():.0f}",
                f"{df_month['sell_price'].sum():.0f}",
                f"{df['sell_price'].sum():.0f}"
            ],
            "Marge (€)": [
                f"{df_today['margin'].sum():.0f}",
                f"{df_week['margin'].sum():.0f}",
                f"{df_month['margin'].sum():.0f}",
                f"{df['margin'].sum():.0f}"
            ]
        }
        
        stats_df = pd.DataFrame(stats_data)
        st.dataframe(stats_df, use_container_width=True)
        
        # Moyenne par vente
        st.metric(
            "💎 CA moyen par vente",
            f"{df['sell_price'].mean():.0f} €",
            f"Marge moy: {df['margin'].mean():.0f} €"
        )
    
    # Dernières ventes
    st.markdown("---")
    st.subheader("🔄 Dernières ventes")
    
    recent_sales = df.sort_values('sale_date', ascending=False).head(10)
    recent_sales_display = recent_sales[['sale_date', 'title', 'sell_price', 'buy_price', 'margin']].copy()
    recent_sales_display.columns = ['Date', 'Produit', 'Prix vente', 'Prix achat', 'Marge']
    
    st.dataframe(recent_sales_display, use_container_width=True)
    
    # Footer avec dernière mise à jour
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.info(f"📊 {len(df)} ventes au total")
    
    with col2:
        st.success(f"💰 {df['sell_price'].sum():.0f} € de CA total")
    
    with col3:
        st.warning(f"🔄 MAJ: {datetime.now().strftime('%H:%M:%S')}")
    
    # Auto-refresh countdown
    if auto_refresh:
        for i in range(30, 0, -1):
            placeholder.text(f"⏱️ Actualisation dans {i}s")
            countdown.progress((30-i)/30)
            time.sleep(1)
        st.rerun()

if __name__ == "__main__":
    main()