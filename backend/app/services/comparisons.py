def compare(declaration, result, absolute_tolerance=20, percent_tolerance=20, comparable_area=False):
    if not declaration.parcel_id:
        return dict(state="NO_CONCILIADO")
    if (
        declaration.issues
        or result is None
        or result.state in {"INDETERMINADO", "NO_ANALIZADO", "ERROR_ANALISIS"}
    ):
        return dict(state="REVISION_REQUERIDA")
    declared, detected = declaration.declared_building, result.state == "CON_CONSTRUCCION_VISIBLE"
    if declared is False and detected:
        return dict(
            state="POSIBLE_CONSTRUCCION_NO_DECLARADA",
            warning="Indicio para revisión administrativa, sin determinación jurídica.",
        )
    if declared is True and not detected:
        return dict(
            state="CONSTRUCCION_DECLARADA_NO_VISIBLE",
            warning="La fecha de imagen, oclusiones o el modelo pueden explicar la diferencia.",
        )
    area = declaration.declared_m2
    if area is not None and result.m2_huella_detectada is not None:
        difference = result.m2_huella_detectada - area
        percent = difference / area * 100 if area > 0 else None
        warning = (
            None
            if comparable_area
            else "Superficie declarada total y huella aérea pueden no ser equivalentes; no se clasifica diferencia de superficie."
        )
        discrepancy = (
            comparable_area
            and abs(difference) > absolute_tolerance
            and (percent is None or abs(percent) > percent_tolerance)
        )
        return dict(
            state="DIFERENCIA_DE_SUPERFICIE" if discrepancy else "CONCORDANCIA",
            difference_m2=difference,
            difference_pct=percent,
            warning=warning,
        )
    return dict(state="CONCORDANCIA" if declared is not None else "REVISION_REQUERIDA")
