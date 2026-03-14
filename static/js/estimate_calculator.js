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
    // --- 3章：計算ロジック ---
    // ==========================================
    /**
     * 4本特価（セット価格）を考慮して、その行の小計を算出する
     */
    function calculateRow($row) {
        // 入力された数量を取得（未入力や文字なら0にする）
        const quantity = parseInt($row.find('input[name$="-quantity"]').val()) || 0;
        // 保持しておいた単価データを取得
        const normalPrice = parseFloat($row.data('unit-price')) || 0;
        const setPrice = parseFloat($row.data('set-price')) || 0;

        let subtotal = 0;
        // セット価格が設定されている場合：4本ごとにセット価格を適用、余りは通常単価
        if (setPrice > 0) {
            const sets = Math.floor(quantity / 4); // 何セットあるか
            const remainder = quantity % 4;        // セットにならない端数
            subtotal = (sets * setPrice) + (remainder * normalPrice);
        } else {
            // セット価格がない場合は単純に 数量×単価
            subtotal = quantity * normalPrice;
        }

        // 行の小計表示を更新（HTML側に「円」が既にあるため、数値のみ表示）
        $row.find('.js-subtotal').text(subtotal.toLocaleString());

        // 行が変われば全体の合計も変わるため、全体計算を呼び出す
        updateGrandTotalWithCharges();
    }

    /**
     * サーバー（Django）に現在の選択内容を送り、工賃などの諸費用を計算してもらう
     */
    function updateEstimateCharges() {
        const purchaseType = $('select[name="purchase_type"]').val();
        const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
        const $chargeSection = $('#charge-section'); // 諸費用を表示するエリア
        const $container = $('#js-charges-container');

        // 「交換」の文字が含まれない区分（持ち帰り等）なら諸費用は不要なので隠す
        if (!purchaseTypeText.includes("交換")) {
            $chargeSection.hide();
            // 諸費用を空にして合計を更新
            $container.empty();
            finalTotalUpdateOnly();
            return;
        }

        $chargeSection.show();
        const items = [];
        // 現在画面にある全行を走査し、有効な入力（タイヤと数量があるもの）をリスト化
        $('.formset-row').not('.empty-form').each(function() {
            const tireId = $(this).find('select[name$="-tire"]').val();
            const quantity = parseInt($(this).find('input[name$="-quantity"]').val()) || 0;
            if (tireId && quantity > 0) {
                items.push({ tire_id: tireId, quantity: quantity });
            }
        });

        if (items.length === 0) {
            $container.html('<tr><td colspan="4" class="text-muted text-center py-3 small">タイヤを選択し数量を入力すると、工賃が自動計算されます</td></tr>');
            return;
        }

        // 非同期通信（AJAX）で工賃計算APIを叩く
        $.ajax({
            url: '/estimate/api/calculate-charges/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ items: items, purchase_type: purchaseType }),
            headers: { 'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').val() },
            success: function(response) {
                $container.empty();
                if (response.charges && response.charges.length > 0) {
                    let html = '';
                    response.charges.forEach((c) => {
                        html += `<tr>
                            <td>${c.name}</td>
                            <td class="text-end">${Number(c.price).toLocaleString()}円</td>
                            <td class="text-center">
                                <input type="number" class="charge-qty-input form-control form-control-sm d-inline-block" style="width: 70px;" value="${c.qty}" data-price="${c.price}">
                            </td>
                            <td class="text-end charge-subtotal-display">${Number(c.subtotal).toLocaleString()}円</td>
                        </tr>`;
                    });
                    $container.html(html);
                }
                // 工賃が確定したので最終的な総合計を計算
                finalTotalUpdateOnly(); 
            }
        });
    }

    // ==========================================
    // --- 4章：Formset動的行追加（プロ仕様） ---
    // ==========================================
    /**
     * 新しい明細行を追加する。Django Formsetの仕様(TOTAL_FORMS管理)を厳守する
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

        $newRow.find('.js-unit-price, .js-set-price, .js-subtotal').text('0'); // 初期表示は0
        $newRow.data('unit-price', 0).data('set-price', 0); // データ属性もリセット

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
        if (isOk && totalQty > 0) {
            updateEstimateCharges(); 
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
        // 総計には「円」を表示する
        $('#js-grand-total').attr('data-total', total).text(total.toLocaleString() + "円");
    }

    // ==========================================
    // --- 6章：表示制御 ＆ 監視 ---
    // ==========================================
    /**
     * 画面表示とボタン制御
     * @returns {boolean} エラーがなければtrue
     */
    function updateGrandTotalDisplay(finalTotal, errorMsg) {
        const $msgArea = $('#validation-error-msg');
        const $totalDisplay = $('#js-grand-total');
        const $btn = $('button[type="submit"]');

        // 総計表示。0円時などの色制御のためdata-totalを更新し、単位「円」を付与
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
        updateTireInfo($(this).closest('tr'));
    });

    // 数量の変更時
    $(document).on('input change', 'input[name$="-quantity"]', function() {
        calculateRow($(this).closest('tr'));
    });

    // 購入区分の変更時
    $(document).on('change', 'select[name="purchase_type"]', function() {
        updateGrandTotalWithCharges();
    });

    // 明細行の追加ボタン
    $(document).on('click', '#add-row-btn', function(e) {
        e.preventDefault();
        addFormsetRow();
    });

    // 工賃数量の手動変更時
    $(document).on('input change', '.charge-qty-input', function() {
        const qty = parseFloat($(this).val()) || 0;
        const price = parseFloat($(this).data('price')) || 0;
        $(this).closest('tr').find('.charge-subtotal-display').text((qty * price).toLocaleString() + "円");
        finalTotalUpdateOnly();
    });

});