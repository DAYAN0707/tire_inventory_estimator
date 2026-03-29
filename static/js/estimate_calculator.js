/**
 * 見積計算 ＆ 動的行追加スクリプト（完全プロフェッショナル仕様）
 * 全体の流れ：
 * 1章：データの準備と初期設定
 * 2章：タイヤ選択時のマスタデータ紐付け
 * 3章：金額計算ロジック（行単位 ＆ 諸費用API）
 * 4章：Django Formsetの整合性を保つ動的行追加
 * 5章：全体の集計 ＆ リアルタイム・バリデーション
 * 6章：ユーザー操作の監視（イベントリスナー）
 * 7章：タイヤ行削除（Formset対応）
 */

// 🔥 修正の本質：どの項目を手入力したかをキー単位（masterId_rowIndex）で記録する
let manualEditedKeys = new Set(); 
let chargeUpdateTimer; // Debounce（連打防止）用のタイマー

console.log("★★★ JSファイル読み込み成功！ ★★★");

$(function() {
    console.log("見積計算スクリプト始動");

    // ==========================================
    // --- 1章：初期化・マスタ読み込み ---
    // ==========================================
    // HTML内に埋め込まれたJSON（タイヤの単価や特価情報）を取得
    const tireMasterElement = document.getElementById('tire-master-data');
    const tireMasterData = JSON.parse(tireMasterElement?.textContent || "[]");

    // ==========================================
    // --- 2章：タイヤ金額計算（単価・小計） ---
    // ==========================================
    /**
     * タイヤ1行分の金額（単価・小計）を更新するメイン関数
     * 1. 選択されたタイヤを特定
     * 2. 特価適用の判定
     * 3. 画面表示の更新
     */
    function updateTireInfo($row) {
        // プルダウンから現在選択されているタイヤのIDを取得
        const tireId = $row.find('select[name$="-tire"]').val();
        // 入力されている数量を取得
        const qty = parseInt($row.find('input[name$="-quantity"]').val(), 10) || 0;
        
        // 🎯 マスタデータから該当するタイヤを探す
        const tire = tireMasterData.find(t => t.id == tireId);

        // 🎯 デバッグ用：マスタデータの中身をコンソールに表示して確認
        console.log("🔍 選択されたタイヤデータ:", tire);

        if (tire) {
            // --- 特価判定ロジック ---
            // 🎯 【重要】プロパティ名をマスタ(unit_price / set_price)に合わせて修正
            // 数量が4の倍数の場合に「4本特価(set_price)」を適用する
            const isSpecialPrice = (qty > 0 && qty % 4 === 0 && tire.set_price);
            
            // 特価なら1本当たり単価を算出、そうでなければ通常単価を採用
            const unitPrice = isSpecialPrice 
                ? Math.floor(tire.set_price / 4) 
                : (tire.unit_price || 0);
            
            // --- 画面表示（UI）の更新 ---
            // 1. 通常単価の表示
            const $unitPriceCell = $row.find('.js-unit-price, .unit-price-display');
            $unitPriceCell.text(Number(tire.unit_price || 0).toLocaleString() + "円");

            // 2. 4本特価の表示
            const $specialPriceCell = $row.find('.js-set-price, .special-price-display');
            $specialPriceCell.text(tire.set_price ? Number(tire.set_price).toLocaleString() + "円" : "---");
            
            // --- 小計の計算 ---
            const subtotal = unitPrice * qty;

            // 3. 小計表示を更新
            const $subtotalCell = $row.find('.js-subtotal, .item-subtotal-display');
            $subtotalCell.text(subtotal.toLocaleString() + "円");
            
            // 🎯 【重要】計算に使った数値をdata属性に保持（後で総合計の計算時に集計するため）
            $subtotalCell.data('value', subtotal);
            
            console.log(`✅ 行計算完了: ID=${tireId}, 数量=${qty}, 小計=${subtotal}`);
        } else {
            // タイヤが選択されていない、または削除された場合は表示をリセット
            $row.find('.js-unit-price, .unit-price-display, .js-set-price, .special-price-display, .js-subtotal, .item-subtotal-display').text("---");
            $row.find('.js-subtotal, .item-subtotal-display').data('value', 0);
        }
        
        // 🎯 タイヤの金額が変わったので、最後に総合計（タイヤ＋諸費用）を再計算
        if (typeof finalTotalUpdateOnly === 'function') {
            finalTotalUpdateOnly();
        }
    }

    // ==========================================
    // --- 3章：諸費用計算ロジック（IDベース・安定版） ---
    // ==========================================
    
    /**
     * 🔥 入力連打でAPIが火を吹かないよう制御（Debounce）
     */
    function updateEstimateChargesDebounced() {
        clearTimeout(chargeUpdateTimer);
        chargeUpdateTimer = setTimeout(() => {
            updateEstimateCharges();
        }, 200); 
    }

    /**
     * 諸費用の計算・再描画を行うメイン関数
     */
    function updateEstimateCharges() {
        let chargeDict = {};
        let totalWorkQty = 0; 

        $('.charge-qty-input').each(function() {
            const name = $(this).attr('name');
            const qtyStr = $(this).val();
            const qty = parseInt(qtyStr, 10) || 0;

            if (name) {
                const keyMatch = name.match(/\[(.*?)\]/); 
                if (keyMatch) {
                    const key = keyMatch[1];
                    chargeDict[key] = (qtyStr === "") ? "0" : qtyStr;
                    if ($(this).closest('tr').find('td:first').text().includes("工賃")) {
                        totalWorkQty += qty;
                    }
                }
            }
        });

        const isFirstLoad = Object.keys(chargeDict).length === 0;

        const items = [];
        $('.formset-row:visible').not('.empty-form').each(function() {
            const tireId = $(this).find('select[name$="-tire"]').val();
            const quantity = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
            if (tireId) {
                items.push({ tire_id: tireId, quantity: quantity });
            }
        });

        $.ajax({
            url: '/estimate/api/calculate-charges/',
            type: 'POST',
            contentType: 'application/json',
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() },
            data: JSON.stringify({ 
                items: items, 
                purchase_type: $('#id_purchase_type').val() || $('select[name="purchase_type"]').val(),
                charge_qtys: isFirstLoad ? null : chargeDict,
                total_work_qty: isFirstLoad ? null : totalWorkQty 
            }),
            success: function(response) {
                console.log("★★★ API Response ★★★", response.charges);
                const $container = $('#js-charges-container');
                if ($container.length === 0) return;

                $container.empty();

                if (response.charges && response.charges.length > 0) {
                    let html = '';
                    response.charges.forEach(function(c) { 
                        const key = `${c.master_id}_${c.row_idx ?? 0}`;
                        const $existing = $(`input[name="charge_qtys[${key}]"]`);
                        
                        let qty;
                        if (manualEditedKeys.has(key) && $existing.length) {
                            qty = $existing.val(); 
                        } else {
                            qty = Number(c.qty || 0);
                        }

                        const canEdit = c.is_editable; 
                        const readonlyAttr = canEdit 
                            ? "" 
                            : "readonly tabindex='-1' style='background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6; pointer-events: none;'";

                        const rowClass = (qty == 0) ? 'charge-row-zero text-muted opacity-50' : '';

                        html += `
                            <tr class="charge-row ${rowClass}">
                                <td>${c.name}</td>
                                <td class="text-end">${Number(c.price).toLocaleString()}円</td>
                                <td class="text-center">
                                    <input type="number" min="0" value="${qty}"
                                        name="charge_qtys[${key}]" 
                                        class="charge-qty-input form-control form-control-sm d-inline-block" 
                                        style="width: 70px;"
                                        data-price="${c.price}"
                                        data-row-idx="${c.row_idx ?? 0}"
                                        ${readonlyAttr}>
                                    <input type="hidden" name="charge_master_ids[]" value="${c.master_id}">
                                </td>
                                <td class="text-end charge-subtotal-display">${(qty * c.price).toLocaleString()}円</td>
                            </tr>`;
                    });
                    $container.html(html);
                } else {
                    $container.html('<tr><td colspan="4" class="text-center text-muted py-3">タイヤを選択すると工賃が自動計算されます</td></tr>');
                }
                
                finalTotalUpdateOnly(); 
            },
            error: function(xhr) {
                console.error("API Error:", xhr.responseText);
            }
        }); 
    }

    // ==========================================
    // --- 4章：タイヤ明細の行計算 ＆ 行追加 ---
    // ==========================================
    
    /**
     * 特定のタイヤ明細行（tr）の小計を算出
     */
    function calculateRow($row) {
        // 2章の新しい updateTireInfo に処理を委譲
        updateTireInfo($row);
        // バリデーションと諸費用の更新へ
        updateGrandTotalWithCharges();
    }

    /**
     * Django Formsetの仕様に準拠した動的行追加
     */
    function addFormsetRow() {
        const $totalForms = $('#id_items-TOTAL_FORMS');
        const formCount = parseInt($totalForms.val());

        const $firstRow = $('.formset-row').first();
        const $newRow = $firstRow.clone(true); 

        $newRow.find('input, select').each(function() {
            const name = $(this).attr('name');
            const id = $(this).attr('id');
            if (name) $(this).attr('name', name.replace(/-\d+-/, `-${formCount}-`));
            if (id) $(this).attr('id', id.replace(/-\d+-/, `-${formCount}-`));
            $(this).val(""); 
        });

        // 初期表示をリセット
        $newRow.find('.js-unit-price, .js-set-price, .js-subtotal, .unit-price-display, .special-price-display, .item-subtotal-display').text('---'); 
        $newRow.find('.item-subtotal-display').data('value', 0);

        $('.formset-row').last().after($newRow);
        $totalForms.val(formCount + 1); 
        updateGrandTotalWithCharges();
    }

    // ==========================================
    // --- 5章：総合計 ＆ バリデーション統合 ---
    // ==========================================
    
    /**
     * 画面上の全数値を合算し、業務ルール（制限）をチェックする重要関数
     */
    function updateGrandTotalWithCharges() {
        let totalQty = 0;
        let tireTypes = new Set();

        // 可視状態（削除されていない）のタイヤ行をスキャン
        $('.formset-row:visible').not('.empty-form').each(function() {
            const qty = parseInt($(this).find('input[name$="-quantity"]').val(), 10) || 0;
            const tireId = $(this).find('select[name$="-tire"]').val();
            if (tireId && qty > 0) {
                totalQty += qty;
                tireTypes.add(tireId);
            }
        });

        // 購入区分のテキストまたはIDを取得して判定
        const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
        const purchaseVal = $('#id_purchase_type').val() || $('select[name="purchase_type"]').val();
        let errorMsg = "";

        // 🎯 業務バリデーション：交換作業時のルール（value="exchange" または テキストに"交換"を含む場合）
        if ((purchaseVal === "exchange" || purchaseTypeText.includes("交換")) && totalQty > 0) {
            if (totalQty > 8) {
                errorMsg = `【本数制限エラー】現在 ${totalQty} 本選択中です。交換作業ご希望の場合は、最大8本までにしてください。`;
            } 
            else if (tireTypes.size > 2) {
                errorMsg = `【台数制限エラー】現在 ${tireTypes.size} 種類のタイヤが選択されています。交換作業ご希望の場合は、1台分(前後サイズ違いのお車など、最大2サイズ選択可能)までにしてください。`;
            }
        }

        const isOk = updateGrandTotalDisplay(errorMsg);
        
        // 🎯 【復活】エラーがない場合のみ諸費用を再計算する
        if (isOk) {
            updateEstimateChargesDebounced();
        } else {
            // エラーがある場合は諸費用を隠すか薄くする
            $('#js-charges-container').css('opacity', '0.5');
        }
        return isOk;
    }

    /**
     * 表示の最終合算と保存ボタンの制御
     */
    function finalTotalUpdateOnly() {
        let total = 0;
        // タイヤの小計と諸費用の小計をすべて集計
        $('.js-subtotal, .item-subtotal-display, .charge-subtotal-display').each(function() {
            const txt = $(this).text().replace(/[^\d]/g, '');
            total += parseFloat(txt) || 0;
        });
        $('#js-grand-total').text(total.toLocaleString() + "円");
    }

    function updateGrandTotalDisplay(errorMsg) {
        const $msgArea = $('#validation-error-msg');
        finalTotalUpdateOnly();
        
        if (errorMsg) {
            // エラー表示を出し、送信ボタンを隠す
            if ($msgArea.length === 0) {
                // メッセージエリアがない場合は動的に作成
                $('.tire-table').before('<div id="validation-error-msg" class="alert alert-danger"></div>');
                return updateGrandTotalDisplay(errorMsg); // 再帰呼び出し
            }
            $msgArea.text(errorMsg).addClass('bg-danger').show();
            $('button[type="submit"]').hide(); 
            return false;
        } else {
            $msgArea.hide();
            $('button[type="submit"]').show(); 
            $('#js-charges-container').css('opacity', '1');
            return true;
        }
    }

    // ===================================================
    // --- 6章：ユーザー操作の監視（イベントリスナー） ---
    // ===================================================

    $(document).ready(function() {
        console.log("🚀 見積計算JS: 初期化開始");

        // ページ読み込み時に初回バリデーションと計算を実行
        updateGrandTotalWithCharges();

        /**
        * 1. タイヤの種類・本数・購入区分が変わった時の連動
        */
        $(document).on('change', 'select[name$="-tire"], input[name$="-quantity"], select[name="purchase_type"], #id_purchase_type', function() {
            console.log("🔄 タイヤ構成の変更を検知しました");
            
            const $row = $(this).closest('tr');
            
            // ① 金額表示の更新
            if ($row.hasClass('formset-row')) {
                updateTireInfo($row); 
            }

            // ② 諸費用の手動ロックをリセット
            manualEditedKeys.clear(); 
        
            // ③ バリデーション実行（この中で諸費用の再計算APIが呼ばれる）
            updateGrandTotalWithCharges();
        });

        /**
        * 2. 諸費用の数量を手入力した際のロック処理
        */
        $(document).on('input', '.charge-qty-input', function() {
            const name = $(this).attr('name');
            const keyMatch = name ? name.match(/\[(.*?)\]/) : null;
        
            if (keyMatch) {
                const fullKey = keyMatch[1];
                manualEditedKeys.add(fullKey); 
                console.log("🛠 手動編集（行単位ロック）:", fullKey);
            }

            const $row = $(this).closest('tr');
            const qty = parseFloat($(this).val()) || 0;
            const price = parseFloat($(this).data('price')) || 0;

            $row.find('.charge-subtotal-display').text((qty * price).toLocaleString() + "円");
        
            if (qty == 0) {
                $row.addClass('charge-row-zero text-muted opacity-50');
            } else {
                $row.removeClass('charge-row-zero text-muted opacity-50');
            }

            finalTotalUpdateOnly(); 
            updateEstimateChargesDebounced();
        });

        /**
        * 3. 行追加・削除ボタンのイベント
        */
        $('#add-row-btn').on('click', function(e) { 
            e.preventDefault(); 
            addFormsetRow(); 
        });

        /**
         * 4. フォーム送信時の最終防衛ライン
         */
        $('form').on('submit', function(e) {
            if (!updateGrandTotalWithCharges()) {
                e.preventDefault();
                alert("タイヤ構成にエラーがあるため、見積を確定できません。");
            }
        });

        console.log("✅ 全イベントリスナーの登録完了");
    });

    // ==========================================
    // --- 7章：タイヤ行削除（Formset対応） ---
    // ==========================================
    $(document).on('click', '.delete-tire-row', function() {
        if ($('.formset-row:visible').length <= 1) {
            alert("最低1行は残してください。");
            return;
        }

        const $row = $(this).closest('.formset-row');
        const $deleteInput = $row.find('input[type="checkbox"][name$="-DELETE"]');
        if ($deleteInput.length) $deleteInput.prop('checked', true);

        $row.hide(); 
        $row.find('input[name$="-quantity"]').val(0); 
        
        manualEditedKeys.clear(); 
        updateGrandTotalWithCharges();
        console.log("🗑 行を削除し、再計算を実行しました");
    });
});