/**
 * 見積計算 ＆ 動的行追加スクリプト（完全プロフェッショナル仕様）
 * * 全体の流れ：
 * 1章：データの準備と初期設定
 * 2章：タイヤ選択時のマスタデータ紐付け
 * 3章：金額計算ロジック（行単位 ＆ 諸費用API）
 * 4章：Django Formsetの整合性を保つ動的行追加
 * 5章：全体の集計 ＆ リアルタイム・バリデーション
 * 6章：ユーザー操作の監視（イベントリスナー）
 */
let isManualEditing = false;

console.log("★★★ JSファイル読み込み成功！ ★★★");

// フォーム送信時のログ出力設定
$('#estimate-form').on('submit', function() {
    // 完全に一致する名前で取得する
    const qtys = {};
    $('input[name^="charge_qtys"]').each(function(){
        const name = $(this).attr('name'); // charge_qtys[4_0]
        const key = name.match(/\[(.*?)\]/)[1]; // 4_0
        qtys[key] = $(this).val();
    });
    console.log("🚀 送信直前 qtys:", qtys);

    const ids = $('input[name="charge_master_ids[]"]').map(function(){ return $(this).val(); }).get();
    console.log("🚀 送信直前！ IDリスト:", ids);
});

$(function() {
    console.log("見積計算スクリプト始動");

    // ==========================================
    // --- 1章：初期化・マスタ読み込み ---
    // ==========================================
    // HTML内に埋め込まれたJSON（タイヤの単価や特価情報）を取得
    const tireMasterElement = document.getElementById('tire-master-data');
    // 要素が存在しない場合は空配列 [] を代入してエラーを防ぐ
    const tireMasterData = JSON.parse(tireMasterElement?.textContent || "[]");

    // ==========================================
    // --- 2章：タイヤ情報の反映・行単価の取得 ---
    // ==========================================
    /**
     * 選択されたタイヤIDを元に、単価情報をHTML要素の「データ属性」に保存する
     * @param {jQuery} $row - 操作対象の明細行（tr要素など）
     */
    function updateTireInfo($row) {
        // プルダウンから現在選択されているタイヤのIDを取得
        const tireId = $row.find('select[name$="-tire"]').val();
        // マスタデータの中からIDが一致するものを探す
        const tireData = tireMasterData.find(t => t.id == tireId);

        if (tireData) {
            // 後で計算に使いやすいよう、行要素自体に単価を隠し持たせる（data属性）
            $row.data('unit-price', tireData.unit_price || 0);
            $row.data('set-price', tireData.set_price || 0);

            // 画面上の「単価」と「4本特価」の表示を更新
            $row.find('.js-unit-price').text(Number(tireData.unit_price).toLocaleString() + "円");
            $row.find('.js-set-price').text(Number(tireData.set_price).toLocaleString() + "円");
        } else {
            $row.data('unit-price', 0);
            $row.data('set-price', 0);
            $row.find('.js-unit-price, .js-set-price').text("-");
        }
        // 単価が変わったので、その行の小計を再計算する
        calculateRow($row);
    }

// ==========================================
    // --- 3章：諸費用計算ロジック ---
    // ==========================================
    /**
     * 諸費用の計算・再描画を行う関数
     * タイヤの選択や本数が変わるたびに呼び出され、API経由で最新の諸費用を取得
     */
    function updateEstimateCharges() {
        
        // 1. 諸費用の入力値を「常に」集める
        // ユーザーが手動で打ち込んだ「廃タイヤ本数」などを、再描画後も引き継ぐための処理
        let chargeDict = {};

        // 🎯 isManualEditing の判定を消して、常に画面上の input をスキャン
        // これにより、API送信時に手入力データが空 {} になるのを防ぐ
        $('.charge-qty-input').each(function() {
            const name = $(this).attr('name'); // 例: "charge_qtys[12_0]"
            const qty = $(this).val();

            if (name) {
                // [ ] の中身（"12_0" など）を抽出して、Pythonが理解できるキー形式に！！！
                const keyMatch = name.match(/\[(.*?)\]/);
                if (keyMatch) {
                    const key = keyMatch[1];
                    chargeDict[key] = qty; // 例 -> "12_0": "2"
                }
            }
        });

        // 🚀 【新規追加】初回は空なら送らない（←これが超重要：廃タイヤ4本を実現するため）
        // 画面にまだ諸費用行がない、または入力が一切ない場合は初回とみなす
        const isFirstLoad = Object.keys(chargeDict).length === 0;

        // 🚀 これで Network タブの Payload に数字が載る！
        console.log("🔥 送信直前 chargeDict:", chargeDict);
        
        // 🎯【ここが修正ポイント！】タイヤ明細からデータを直接集める
        const items = [];
        $('.formset-row').not('.empty-form').each(function() {
            // Djangoのname属性（items-0-tire など）から値を取得
            const tireId = $(this).find('select[name$="-tire"]').val();
            const quantity = parseInt($(this).find('input[name$="-quantity"]').val()) || 0;

            if (tireId && quantity > 0) {
                items.push({
                    tire_id: tireId,
                    quantity: quantity
                });
            }
        });

        // 🔥 デバッグ：ここが空 [ ] じゃなくなれば成功！
        console.log("🔥 送信直前 items:", items);

        const purchaseType = $('#id_purchase_type').val();

        // 2. 非同期通信（AJAX）でサーバーに計算を依頼
        $.ajax({
            url: '/estimate/api/calculate-charges/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ 
                items: items, 
                purchase_type: purchaseType,
                // 🎯 【新規追加】初回なら null を送り、Python側のデフォルト計算（合計4本など）を動かす
                charge_qtys: isFirstLoad ? null : chargeDict 
            }),
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() },
            
            success: function(response) {
                /**
                 * 🔍 デバッグ用：サーバーから届いた計算データを確認
                 */
                console.log("★★★ API Response ★★★", response.charges);

                const $container = $('#js-charges-container');
                
                /**
                 * 🔍 開発用：入れ物（tbody）が正しく見つかっているか確認
                 */
                if ($container.length === 0) {
                    console.error("❌ エラー: #js-charges-container が見つかりません。");
                    return;
                }

                /**
                 * 【重複防止】
                 * 描画を開始する前に、必ず tbody の中身を空っぽ（更地）にする
                 */
                $container.empty();

                // response.charges が存在し、中身がある場合のみ描画処理を行う
                if (response.charges && response.charges.length > 0) {
                    let html = '';

                    /**
                     * 【最重要】forEach の第2引数 'index' を受け取る
                     * これにより、前後サイズ違いの行を 0, 1, 2... と区別
                     */
                    response.charges.forEach((c, index) => { 
                        const name = c.name || "名称未設定";
                        const price = Number(c.price || 0);
                        const qty = Number(c.qty || 0);
                        const subtotal = Number(c.subtotal || 0);

                        /**
                         * ランフラットタイヤの工賃かどうかを判定
                         * 名前に「ランフラット」が含まれる場合は、手入力を禁止（readonly）
                         */
                        // APIから返ってきた c.qty をそのまま使う
                        const isRft = c.name.includes("ランフラット");
                        // RFTなら「入力不可・グレー背景」、それ以外は「入力可」にする
                        const readonlyAttr = isRft 
                        ? "readonly style='width: 70px; background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6; pointer-events: none;'" 
                        : "style='width: 70px;'";

                        /**
                         * HTMLの組み立て
                         * name属性を "charge_qtys[マスターID_行番号]" 形式に設定
                         */
                        // valueに APIから返った c.qty を確実に入れる
                        html += `<tr>
                            <td>${name}</td>
                            <td class="text-end">${price.toLocaleString()}円</td>
                            <td class="text-center">
                                <input type="number" 
                                    name="charge_qtys[${c.master_id}_${index}]" 
                                    class="charge-qty-input form-control form-control-sm d-inline-block" 
                                    value="${c.qty}" 
                                    data-price="${price}"
                                    ${readonlyAttr}>
                                <input type="hidden" 
                                    name="charge_master_ids[${c.master_id}_${index}]" 
                                    value="${c.master_id}">
                            </td>
                            <td class="text-end charge-subtotal-display">${subtotal.toLocaleString()}円</td>
                        </tr>`;
                    });

                    // 組み立てたHTMLをテーブルへ流し込む
                    $container.html(html);
                } else {
                    $container.html('<tr><td colspan="4" class="text-center text-muted">諸費用データがありません</td></tr>');
                }

                /**
                 * 見積書全体の「総計（税込）」を再計算
                 */
                finalTotalUpdateOnly();

                console.log("✅ 諸費用テーブルの描画が完了しました（Index付き）");
            },

            error: function(xhr) {
                console.error("API Error:", xhr.responseText);
            }
        }); 
    } // 🎯 updateEstimateCharges 終了

    // リアルタイム連動のトリガー
    // 工賃などの数量が変わったら、即座にAPIを叩いてRFT加算なども再計算させる
    $(document).on('input', '.charge-qty-input', function() {
        updateEstimateCharges();
    });


    // ==========================================
    // --- 4章：タイヤ明細の行計算 (calculateRow) ---
    // ==========================================
    /**
     * 特定のタイヤ明細行（tr）の小計を計算する
     */
    function calculateRow($row) {
        // 数量と単価を取得
        const qty = parseInt($row.find('input[name$="-quantity"]').val()) || 0;
        const priceText = $row.find('.js-unit-price').text().replace(/[^\d]/g, '');
        const price = parseInt(priceText) || 0;

        // 小計を算出
        const subtotal = qty * price;

        // 画面の小計表示を更新
        $row.find('.js-subtotal').text(subtotal.toLocaleString() + "円");

        // 🎯 タイヤの数量が変わったので、諸費用も再計算させる
        updateGrandTotalWithCharges();
    }


    // ==========================================
    // --- 4章：Formset動的行追加（プロ仕様） ---
    // ==========================================
    /**
     * 新しい明細行を追加する。Django Formsetの仕様(TOTAL_FORMS管理)を厳守
     */
    function addFormsetRow() {
        const $totalForms = $('#id_items-TOTAL_FORMS');
        const formCount = parseInt($totalForms.val());

        const $firstRow = $('.formset-row').first();
        const $newRow = $firstRow.clone(true); 

        $newRow.find('input, select').each(function() {
            const $el = $(this);
            const name = $el.attr('name');
            const id = $el.attr('id');

            if (name) $el.attr('name', name.replace(/-\d+-/, `-${formCount}-`));
            if (id) $el.attr('id', id.replace(/-\d+-/, `-${formCount}-`));

            if ($el.is('select')) {
                $el.prop('selectedIndex', 0);
            } else if ($el.attr('type') === 'checkbox') {
                $el.prop('checked', false);
            } else {
                $el.val('');
            }
        });

        $newRow.find('.js-unit-price, .js-set-price, .js-subtotal').text('0'); 
        $newRow.data('unit-price', 0).data('set-price', 0); 

        $('.formset-row').last().after($newRow);
        $totalForms.val(formCount + 1);
        
        updateGrandTotalWithCharges();
    }


    // ==========================================
    // --- 5章：総合計 ＆ バリデーション統合 ---
    // ==========================================
    /**
     * 画面上の全ての金額を合算し、同時にビジネスルール（本数制限など）をチェックする
     */
    function updateGrandTotalWithCharges() {
        let tireTotal = 0;
        let totalQty = 0;
        let tireTypes = new Set();

        // A. タイヤ代の集計
        $('.formset-row').not('.empty-form').each(function() {
            const subtotalText = $(this).find('.js-subtotal').text().replace(/[^\d]/g, '');
            tireTotal += parseFloat(subtotalText) || 0;

            const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
            const tireId = $(this).find('select[name$="-tire"]').val();

            if (tireId && tireId.trim() !== "" && qty > 0) {
                totalQty += qty;
                tireTypes.add(tireId);
            }
        });

        // B. 諸費用の集計
        let chargeTotal = 0;
        $('.charge-subtotal-display').each(function() {
            const txt = $(this).text().replace(/[^\d]/g, '');
            chargeTotal += parseFloat(txt) || 0;
        });

        const finalTotal = tireTotal + chargeTotal;

        // C. バリデーション判定
        const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
        let errorMsg = "";

        if (purchaseTypeText.includes("交換") && totalQty > 0) {
            if (totalQty > 8) {
                errorMsg = `【本数制限エラー】現在 ${totalQty} 本選択中です。交換作業ご希望の場合は、最大8本までにしてください。`;
            } else if (tireTypes.size > 2) {
                errorMsg = `【台数制限エラー】現在 ${tireTypes.size} サイズ選択中です。交換作業ご希望の場合は、1台分（前後サイズ違いのお車など、最大2サイズ選択可能）までにしてください。`;
            }
        }

        // D. 画面表示への反映
        const isOk = updateGrandTotalDisplay(finalTotal, errorMsg);

        // エラーがなく、かつタイヤが選択されている場合のみ、諸費用APIを叩きにいく
        // ※updateEstimateChargesDebounced はグローバル等で定義されている前提
        if (isOk && totalQty > 0) {
            if (typeof updateEstimateChargesDebounced === 'function') {
                updateEstimateChargesDebounced();
            } else {
                updateEstimateCharges();
            }
        }
    }

    /**
     * API更新後などに、純粋に画面上の数値を合計して表示する補助関数
     */
    function finalTotalUpdateOnly() {
        let total = 0;
        $('.js-subtotal, .charge-subtotal-display').each(function() {
            const txt = $(this).text().replace(/[^\d]/g, '');
            total += parseFloat(txt) || 0;
        });
        $('#js-grand-total').attr('data-total', total).text(total.toLocaleString() + "円");
    }


    // ==========================================
    // --- 6章：表示制御 ＆ 監視 ---
    // ==========================================
    function updateGrandTotalDisplay(finalTotal, errorMsg) {
        const $msgArea = $('#validation-error-msg');
        const $totalDisplay = $('#js-grand-total');
        const $btn = $('button[type="submit"]');

        $totalDisplay.attr('data-total', finalTotal).text(finalTotal.toLocaleString() + "円");

        if (errorMsg) {
            $msgArea.text(errorMsg).addClass('bg-danger').show();
            $btn.hide();
            return false;
        } else {
            $msgArea.hide().text("");
            $btn.show();
            return true;
        }
    }

    /**
     * ユーザー操作のイベントリスナー設定
     */
    // タイヤ選択の変更時
    $(document).on('change', 'select[name$="-tire"]', function() {
        isManualEditing = false; 
        if (typeof updateTireInfo === 'function') {
            updateTireInfo($(this).closest('tr'));
        }
    });

    // 数量の変更時
    $(document).on('input change', 'input[name$="-quantity"]', function() {
        isManualEditing = false; 
        calculateRow($(this).closest('tr'));
    });

    // 購入区分の変更時
    $(document).on('change', 'select[name="purchase_type"]', function() {
        isManualEditing = false;
        updateGrandTotalWithCharges();
    });

    // 明細行の追加ボタン
    $(document).on('click', '#add-row-btn', function(e) {
        e.preventDefault();
        addFormsetRow();
    });

    // 工賃数量の手動変更時
    $(document).on('input change', '.charge-qty-input', function() {
        isManualEditing = true; 
        console.log("🛠 手動編集モードON");
        const qty = parseFloat($(this).val()) || 0;
        const price = parseFloat($(this).data('price')) || 0;
        $(this).closest('tr').find('.charge-subtotal-display').text((qty * price).toLocaleString() + "円");
        finalTotalUpdateOnly();
    });

});