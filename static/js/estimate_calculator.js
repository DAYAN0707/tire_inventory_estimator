/**
 * 見積作成画面用 計算ロジック
 * 役割: タイヤ金額の計算、API連携による諸費用の取得、画面への反映
 */
const EstimateCalculator = {
    // 設定: HTMLのクラス名やIDをここにlet subtotal = 集約（後で変更しやすくするため）
    config: {
        tireSelect: '.js-tire-select',
        quantityInput: '.js-quantity-input',
        purchaseType: 'select[name="purchase_type"]',
        unitPriceText: '.js-unit-price',
        setPriceText: '.js-set-price',
        subtotalText: '.js-subtotal',
        chargesContainer: '#js-charges-container',
        grandTotalText: '#js-grand-total'
    },

    // 1. 初期化
    init: function() {
        const self = this;
        console.log("Estimate Calculator Initialized");

        // イベント設定: タイヤ選択、数量変更、購入区分変更時に計算を実行
        $(document).on('change', `${this.config.tireSelect}, ${this.config.purchaseType}`, () => self.updateAll());
        $(document).on('input', this.config.quantityInput, () => self.updateAll());

        // ページ読み込み時にも一度実行
        this.updateAll();
    },

    // 2. 画面全体の更新処理
    updateAll: async function() {
        let tireItems = [];
        let totalTireAmount = 0;

        // 各明細行（タイヤ）をループして計算
        $('.formset-row').each((index, row) => {
            const $row = $(row);
            const tireId = $row.find(this.config.tireSelect).val();
            const qty = Number($row.find(this.config.quantityInput).val()) || 0;

            // 選択されたタイヤの情報を取得（事前に埋め込まれたデータを利用）
            const tireData = this.getTireData(tireId);

            if (tireData) {
                // タイヤ小計の計算ロジック
                const up = parseFloat(tireData.unit_price) || 0;
                const sp = parseFloat(tireData.set_price) || 0;
                
                // 4本特価の適用判定
                let subtotal = 0;

                if (sp > 0) {
                    const sets = Math.floor(qty / 4);
                    const remainder = qty % 4;
                    subtotal = (sets * sp) + (remainder * up);
                } else {
                    subtotal = up * qty;
                }
                
                // 表示更新
                $row.find(this.config.unitPriceText).text(up.toLocaleString() + '円');
                $row.find(this.config.setPriceText).text(sp > 0 ? sp.toLocaleString() + '円' : '-');
                $row.find(this.config.subtotalText).text(subtotal.toLocaleString() + '円');

                totalTireAmount += subtotal;
                tireItems.push({ tire_id: tireId, quantity: qty });
            } else {
                $row.find(`${this.config.unitPriceText}, ${this.config.setPriceText}, ${this.config.subtotalText}`).text('-');
            }
        });

        // 諸費用のAPI呼び出し
        const purchaseType = $(this.config.purchaseType).val();
        await this.updateCharges(tireItems, purchaseType, totalTireAmount);
    },

    // 3. API連携（昨日の calculate_charges_api を呼び出し）
    updateCharges: async function(items, purchaseType, totalTireAmount) {
        try {
            const response = await fetch('/estimate/api/calculate-charges/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({ items: items, purchase_type: purchaseType })
            });

            const data = await response.json();
            let chargesHtml = '';
            let chargesTotal = 0;

            if (data.charges) {
                data.charges.forEach(c => {
                    chargesHtml += `<tr><td>${c.name}</td><td>${c.price.toLocaleString()}円</td><td>${c.qty}</td><td>${c.subtotal.toLocaleString()}円</td></tr>`;
                    chargesTotal += c.subtotal;
                });
            }

            $(this.config.chargesContainer).html(chargesHtml);
            $(this.config.grandTotalText).text((totalTireAmount + chargesTotal).toLocaleString() + '円');

        } catch (error) {
            console.error("Failed to fetch charges:", error);
        }
    },

    // 補助関数: タイヤ情報の取得（HTML側のJSONデータから探す想定）
    getTireData: function(id) {
        const tireDataEl = document.getElementById('tire-master-data');
        if (!tireDataEl) return null;
        const tires = JSON.parse(tireDataEl.textContent);
        return tires.find(t => t.id == id);
    },

    // 補助関数: CSRFトークンの取得
    getCsrfToken: function() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
};

// --- 追加：初期表示の強制リセット ---
    // これにより、HTMLに何が書かれていても、ロード完了時に「0円」
    $('#js-grand-total').text('総合計金額：0 円').css('color', '#d633bb');

// 実行
$(document).ready(() => EstimateCalculator.init());

// ページが読み込まれたら実行
$(function() {
    // ピンクのエラーエリアを探す
    const $alert = $('.alert-danger');
    
    if ($alert.length) {
        let html = $alert.html();
        // [' と '] を力技で空文字に置き換える
        // 念のため、全角や半角のバリエーションも考慮
        let cleanHtml = html.replace(/[\[\]']+/g, ''); 
        
        $alert.html(cleanHtml);
    }
});