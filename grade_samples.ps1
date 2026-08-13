# ============================================================
# ScriptGrader — grade 4 sample answer sheets to populate history
# Run from your project folder: D:\New folder\scriptgrader
# ============================================================

$ApiKey = "67becdc8a1a1bf82a8d20f2790664e75"
$BaseUrl = "http://127.0.0.1:8000"

Add-Type -AssemblyName System.Drawing

function New-AnswerImage {
    param([string]$Text, [string]$OutPath)
    $bmp = New-Object System.Drawing.Bitmap 700, 400
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::White)
    $font = New-Object System.Drawing.Font("Segoe Print", 18)
    if (-not $font.Name -eq "Segoe Print") { $font = New-Object System.Drawing.Font("Comic Sans MS", 18) }
    $brush = [System.Drawing.Brushes]::Black
    $rect = New-Object System.Drawing.RectangleF 20, 20, 660, 360
    $g.DrawString($Text, $font, $brush, $rect)
    $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
}

function Grade-Sample {
    param(
        [string]$QNum, [string]$QText, [string]$ModelAnswer,
        [string]$Rubric, [string]$AnswerText
    )
    $imgPath = "$env:TEMP\sample_$QNum.png"
    $rubricPath = "$env:TEMP\rubric_$QNum.json"
    New-AnswerImage -Text $AnswerText -OutPath $imgPath
    [System.IO.File]::WriteAllText($rubricPath, $Rubric)

    Write-Host "Grading Q$QNum ..."
    $result = curl.exe -s -X POST "$BaseUrl/api/grade" `
        -H "X-API-Key: $ApiKey" `
        -F "sheet_image=@$imgPath;type=image/png" `
        -F "question_number=$QNum" `
        -F "question_text=$QText" `
        -F "model_answer=$ModelAnswer" `
        -F "rubric_json=<$rubricPath"
    Write-Host $result
    Write-Host "---"
}

# ---------- Sample 1: Math — fully correct ----------
Grade-Sample -QNum "1a" `
    -QText "Solve for x: 3x + 7 = 22. Show your working." `
    -ModelAnswer "3x + 7 = 22, so 3x = 15, so x = 5" `
    -Rubric '[{"name":"Correct method","max_marks":2,"description":"isolates the variable correctly"},{"name":"Correct simplification","max_marks":2,"description":"3x = 15"},{"name":"Correct final answer","max_marks":1,"description":"x = 5"}]' `
    -AnswerText "3x + 7 = 22`n3x = 22 - 7`n3x = 15`nx = 5"

# ---------- Sample 2: Math — partial credit, arithmetic slip ----------
Grade-Sample -QNum "1b" `
    -QText "Solve for x: 2x - 4 = 10. Show your working." `
    -ModelAnswer "2x - 4 = 10, so 2x = 14, so x = 7" `
    -Rubric '[{"name":"Correct method","max_marks":2,"description":"isolates the variable correctly"},{"name":"Correct simplification","max_marks":2,"description":"2x = 14"},{"name":"Correct final answer","max_marks":1,"description":"x = 7"}]' `
    -AnswerText "2x - 4 = 10`n2x = 14`nx = 6"

# ---------- Sample 3: Science — mostly correct, missing detail ----------
Grade-Sample -QNum "2a" `
    -QText "Define photosynthesis and name its two main products." `
    -ModelAnswer "Photosynthesis is the process by which plants convert light energy into chemical energy, producing glucose and oxygen." `
    -Rubric '[{"name":"Definition accuracy","max_marks":3,"description":"correctly describes the conversion of light to chemical energy"},{"name":"Names both products","max_marks":2,"description":"mentions both glucose and oxygen"}]' `
    -AnswerText "Photosynthesis is how plants make food`nusing sunlight. It produces oxygen."

# ---------- Sample 4: Science — weak answer, several deductions ----------
Grade-Sample -QNum "2b" `
    -QText "Explain why ice floats on water." `
    -ModelAnswer "Ice is less dense than liquid water because its molecules form a hexagonal crystal lattice with more space between them, so a given mass of ice takes up more volume than the same mass of water." `
    -Rubric '[{"name":"Mentions density","max_marks":2,"description":"states ice is less dense than water"},{"name":"Explains the mechanism","max_marks":3,"description":"describes the crystal lattice / molecular spacing reason"}]' `
    -AnswerText "Ice floats because it is lighter than water."

Write-Host ""
Write-Host "Done. Now check the dashboard: $BaseUrl/dashboard.html"
