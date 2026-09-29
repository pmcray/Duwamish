; =====================================================================
;  META: a tower of interpreters, and the strange loop at its top.
;
;  McCarthy (1960) wrote LISP's evaluator in LISP.  Here that evaluator,
;  M-EVAL, is kept as a quoted list -- data -- and then *installed* by
;  evaluating it.  Because it is data, M-EVAL can also be fed its own
;  source and so interpret itself.  The levels:
;
;     Python  runs  the Model 30 microcode
;     microcode runs TRIAD machine code, compiled from
;     SALISH, which is the TRILISP interpreter, which runs
;     M-EVAL (level 1), which runs
;     M-EVAL again (level 2), which runs  (FACT 2).
;
;  Each level knows nothing of the trits beneath it -- Hofstadter's
;  "levels of description" -- yet the top level is the same text as the
;  one below it.
; =====================================================================
;  Load mceval.lsp first (see jobs/hofstadter.job).
(echo nil)

(define (report level value cost)
  (progn (prin1 "  level ") (prin1 level) (prin1 ":  ") (prin1 target)
         (prin1 " = ") (prin1 value)
         (prin1 ", costing ") (prin1 cost) (print " TRILISP evaluations")))

(define (timed thunk) (let ((e0 (evals))) (let ((v (thunk))) (cons v (- (evals) e0)))))

(print "META: M-EVAL, a LISP written in LISP, interpreting itself")
(terpri)

; level 0: TRILISP itself
(eval fact-source)
(define r0 (timed (lambda () (eval target))))
(report 0 (car r0) (cdr r0))

; level 1: install M-EVAL (evaluate the quoted source), give it FACT
(install mc-source)
(define *m-global* (prims))
(m-run fact-source)
(define r1 (timed (lambda () (m-run target))))
(report 1 (car r1) (cdr r1))

; level 2: M-EVAL reads its own source and becomes the interpreter
(m-setq '*m-global* (prims))
(m-install mc-source)
; the level-1 store now holds the level-2 interpreter's definitions in
; front of the primitives; move the commonest primitives to the front
(setq *m-global* (append (list (cons 'car (cons 'prim car))
                               (cons 'cdr (cons 'prim cdr))
                               (cons 'eq (cons 'prim eq))
                               (cons 'null (cons 'prim null)))
                         *m-global*))
(m-run (list 'm-eval (list 'quote fact-source) nil))
(define r2 (timed (lambda () (m-run (list 'm-eval (list 'quote target) nil)))))
(report 2 (car r2) (cdr r2))

(terpri)
(prin1 "  each level multiplies the cost by about ")
(prin1 (/ (cdr r2) (cdr r1)))
(print " times")
(print "  The level-2 interpreter is the level-1 interpreter's own text, read")
(print "  as data: the program has become the subject of the program.")
