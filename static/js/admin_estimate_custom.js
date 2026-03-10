$(function() {
    console.log("見積計算スクリプト始動");

    /**
     * 1. 【総合計の更新】
     * タイヤ代と諸費用（工賃など）を合算した最終的な金額を画面に表示
     */
    function updateGrandTotal() {
        // 諸費用（手動変更可能）を含めた最新の合計計算関数を呼び出す
        updateGrandTotalWithCharges();
    }

    /**
     * 2. 【タイヤ情報の取得】
     * 選択されたタイヤの単価や4本特価をAPIから取得し、行にデータを保持させる
     */
    function updateTireInfo($row) {
        const tireId = $row.find('select[name$="-tire"]').val();

        // タイヤが変更されるので、一旦表示と保持データをリセット（お掃除）
        $row.find('.unit-price-display').text('0円');
        $row.find('.subtotal-display').text('0円');
        $row.removeAttr('data-unit-price').removeAttr('data-set-price');

        // タイヤが未選択の場合は合計を再計算して終了
        if (!tireId) {
            updateGrandTotal();
            updateEstimateCharges();
            return;
        }

        // サーバーからタイヤの価格情報を取得
        $.getJSON(`/estimate/api/get-tire-info/${tireId}/`, function(data) {
            // 取得した単価・特価を計算用にHTML要素の属性(data-)に保存
            $row.attr('data-unit-price', data.unit_price);
            $row.attr('data-set-price', data.set_price);
            
            // 単価表示エリアの更新（特価がある場合は緑文字で補足）
            let priceHtml = `<div>${data.unit_price.toLocaleString()}円</div>`;
            if (data.set_price > 0) {
                priceHtml += `<div class="text-success" style="font-size: 0.8em;">(4本特価: ${data.set_price.toLocaleString()}円)</div>`;
            }
            $row.find('.unit-price-display').html(priceHtml);
            
            // 金額が変わったので小計と諸費用を再計算
            calculateRow($row);
            updateEstimateCharges();
        });
    }

    /**
     * 3. 【行ごとの小計計算】
     * 本数と単価（または4本特価）を掛け合わせて、その行の金額を出す
     */
    function calculateRow($row) {
        const quantity = parseFloat($row.find('input[name$="-quantity"]').val()) || 0;
        const normalPrice = parseFloat($row.attr('data-unit-price')) || 0;
        const setPrice = parseFloat($row.attr('data-set-price')) || 0;

        let subtotal = 0;
        // 4本特価の設定があり、かつ4本以上購入される場合は特価を適用
        if (setPrice > 0 && quantity >= 4) {
            const setCount = Math.floor(quantity / 4); // 4本セット（整数の商）
            const remainder = quantity % 4;            // セットにならなかった余り（剰余）
            subtotal = (setCount * setPrice) + (remainder * normalPrice);
        } else {
            // 4本未満、または特価設定がない場合は通常単価で計算
            subtotal = quantity * normalPrice;
        }

        // 行の小計を表示し、全体の合計を更新
        $row.find('.subtotal-display').text(subtotal.toLocaleString() + "円");
        updateGrandTotal();
    }

    /**
     * 4. 【諸費用の取得と表示】
     * 作業有の場合に、サーバーから工賃・バルブ・廃タイヤ代を自動取得
     * 表示後はユーザーが数量を自由に書き換えられる
     */
    function updateEstimateCharges() {
        const purchaseType = $('select[name="purchase_type"]').val();
        const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
        const $chargeSection = $('#charge-section');

        // 「持ち帰り」など、作業が含まれない場合は諸費用エリアを隠す
        if (!purchaseTypeText.includes("交換")) {
            $chargeSection.hide();
            return;
        }

        $chargeSection.show();

        // 現在選択されている全てのタイヤ行から「IDと本数」のリストを作成
        const items = [];
        $('.tire-row').each(function() {
            const tireId = $(this).find('select[name$="-tire"]').val();
            const quantity = parseInt($(this).find('input[name$="-quantity"]').val()) || 0;
            if (tireId && quantity > 0) {
                items.push({ tire_id: tireId, quantity: quantity });
            }
        });

        const $container = $('#charge-items-container');

        // タイヤが一つも選ばれていない場合
        if (items.length === 0) {
            $container.html('<p class="text-muted">タイヤを選択すると表示されます</p>');
            return;
        }

        // サーバー側の工賃計算APIを呼び出し
        $.ajax({
            url: '/estimate/api/calculate-charges/',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ items: items, purchase_type: purchaseType }),
            headers: { 'X-CSRFToken': $('input[name$="csrfmiddlewaretoken"]').val() },
            success: function(response) {
                $container.empty();

                if (response.charges && response.charges.length > 0) {
                    // 諸費用テーブルの構築（数量は input タグにして手動変更可能にする）
                    let html = '<table class="table table-sm"><thead><tr><th>項目</th><th>単価</th><th>数量</th><th>小計</th></tr></thead><tbody>';
                    response.charges.forEach((c) => {
                        html += `<tr>
                            <td>${c.name}</td>
                            <td>${c.price.toLocaleString()}円</td>
                            <td>
                                <input type="number" 
                                    class="charge-qty-input form-control form-control-sm" 
                                    style="width: 70px; display: inline-block;"
                                    value="${c.qty}" 
                                    data-price="${c.price}">
                            </td>
                            <td class="charge-subtotal-display">${c.subtotal.toLocaleString()}円</td>
                        </tr>`;
                    });
                    html += '</tbody></table>';
                    
                    // 生成したHTMLを画面に反映
                    $container.html(html);
                } else {
                    $container.append('<p class="text-muted">工賃が見つかりませんでした</p>');
                }
                updateGrandTotal(); 
            }
        });
    }

    /**
     * 5. 【行の追加機能】
     * 複数サイズのタイヤを登録するために、新しい入力行をコピーして増やす
     */
    $(document).on('click', '#add-row-btn', function(e) {
        e.preventDefault();
        const $tableBody = $('.tire-row').closest('tbody');
        const $firstRow = $tableBody.find('.tire-row').first();
        const $newRow = $firstRow.clone(); // 最初の行をコピー

        // コピーした行の中身を空にする
        $newRow.find('select').val('');
        $newRow.find('input').val('');
        $newRow.find('.unit-price-display').text('0円');
        $newRow.find('.subtotal-display').text('0円');
        $newRow.removeAttr('data-unit-price').removeAttr('data-set-price');

        // DjangoのFormsetのID（id_items-0-tireなど）を正しく連番に振り直す
        const totalForms = $('#id_items-TOTAL_FORMS');
        let count = parseInt(totalForms.val());
        $newRow.find('input, select').each(function() {
            const name = $(this).attr('name').replace(/-[0-9]+-/, `-${count}-`);
            $(this).attr('name', name).attr('id', `id_${name}`);
        });

        $tableBody.append($newRow);
        totalForms.val(count + 1); // フォームの総数を更新
    });

    /**
     * 6. 【リアルタイム・イベント監視】
     * ユーザーが操作した瞬間に計算が走るように見張る
     */
    // タイヤが選ばれた時
    $(document).on('change', 'select[name$="-tire"]', function() {
        updateTireInfo($(this).closest('tr'));
    });

    // 持ち帰り・作業有などの区分が変わった時
    $(document).on('change', 'select[name="purchase_type"]', function() {
        updateEstimateCharges();
    });

    // 本数が入力された時
    $(document).on('input', 'input[name$="-quantity"]', function() {
        calculateRow($(this).closest('tr'));
    });

    // 諸費用（工賃など）の数量が手動で書き換えられた時
    $(document).on('input', '.charge-qty-input', function() {
        const $input = $(this);
        const qty = parseFloat($input.val()) || 0;
        const price = parseFloat($input.data('price')) || 0;
        const subtotal = qty * price;
        
        // その行の小計表示を更新し、総合計を出し直す
        $input.closest('tr').find('.charge-subtotal-display').text(subtotal.toLocaleString() + "円");
        updateGrandTotalWithCharges(); 
    });
});

/**
 * 【総合計計算 ＆ 保存制限チェック】
 * タイヤ代 ＋ 諸費用（手動調整後）の合算を行い、作業制限ルールに違反していないか確認
 */
function updateGrandTotalWithCharges() {
    // A. タイヤ明細の合計を計算
    let tireTotal = 0;
    $('.tire-row').each(function() {
        const txt = $(this).find('.subtotal-display').text().replace(/[^\d]/g, '');
        tireTotal += parseFloat(txt) || 0;
    });

    // B. 諸費用（手動入力後の値）の合計を計算
    let chargeTotal = 0;
    $('.charge-subtotal-display').each(function() {
        const txt = $(this).text().replace(/[^\d]/g, '');
        chargeTotal += parseFloat(txt) || 0;
    });

    const finalTotal = tireTotal + chargeTotal;

    // C. バリデーション（作業有の場合の制限チェック）
    const purchaseTypeText = $('select[name="purchase_type"] option:selected').text() || "";
    let totalQty = 0;
    let tireTypes = 0;
    $('.tire-row').each(function() {
        const qty = parseFloat($(this).find('input[name$="-quantity"]').val()) || 0;
        const tireId = $(this).find('select[name$="-tire"]').val();
        if (tireId) { 
            totalQty += qty; 
            tireTypes++; 
        }
    });

    let errorMsg = "";
    if (purchaseTypeText.includes("交換")) {
        // 作業有の場合は「合計8本まで」かつ「最大2サイズまで」
        if (totalQty > 8) {
            errorMsg = `【保存不可】作業有は8本までです（現在 ${totalQty} 本）`;
        } else if (tireTypes > 2) {
            errorMsg = `【保存不可】作業有は2サイズまでです（現在 ${tireTypes} 種）`;
        }
    }

    const $display = $('#grand-total-display');
    const $btn = $('button[type="submit"]');

    // エラーがある場合は赤文字にし、保存ボタンを隠す
    if (errorMsg) {
        $display.css('color', 'red').html(`<strong>${errorMsg}</strong><br>合計金額：${finalTotal.toLocaleString()} 円`);
        $btn.hide();
    } else {
        // 正常な場合はピンクの大きな文字で表示し、保存ボタンを出す
        $display.css('color', '#d633bb').text(`総合計金額：${finalTotal.toLocaleString()} 円`);
        $btn.show();
    }
}